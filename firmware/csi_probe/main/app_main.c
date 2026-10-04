/*
 * EU Twin CSI probe — Phase 0 walk survey firmware for ESP32-C6-DevKitC-1.
 *
 * Based on esp-csi/examples/get-started/csi_recv_router (Apache-2.0):
 * connect to the home router as a station, ping the gateway at a fixed rate
 * and capture CSI from the router's replies.
 *
 * Added for the walk survey:
 *   - every CSI record is sent over UDP to the survey PC (wired to the router)
 *   - BOOT button marks grid points: short press = next point,
 *     long press (>= 2 s) = re-record the previous point
 *   - after a press: 12 s settle (walk away), then 15 s recording window
 *   - RGB LED shows the state: blue = connecting, green = ready,
 *     yellow = walk away, red = recording, purple = long press registered
 */
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "ping/ping_sock.h"

#include "esp_csi_gain_ctrl.h"
#include "led_strip.h"
#include "protocol_examples_common.h"

/* Address of the PC running scripts/csi_receiver.py, as seen from the probe. */
#define TARGET_IP        "192.168.1.100"
#define TARGET_PORT      5005

#define PING_HZ          50
/* Ping target. Empty = the station's gateway. Some routers (e.g. Xiaomi R4A)
 * do not answer pings to themselves; then ping a host behind them, the replies
 * still reach the probe as frames sent by the access point. */
#define PING_TARGET      ""
/* With the Xiaomi R4A no CSI callback ever fires (pings succeed, 2026-10-04),
 * so record the RSSI of every frame the access point transmits instead, via
 * promiscuous mode. Such records have version 2, csi_len 0, and carry the
 * wifi_promiscuous_pkt_type_t (0 = management/beacon, 2 = data) in the
 * first_word_invalid field. Set to 0 to go back to CSI capture. */
#define USE_PROMISCUOUS_RSSI 1
#define BUTTON_GPIO      GPIO_NUM_9   /* BOOT button on ESP32-C6-DevKitC-1 */
#define LED_GPIO         8            /* on-board WS2812, same as esp-radar/console_test */
#define SETTLE_MS        12000  /* walk out of the bathroom, close the door, go to the waiting spot */
#define RECORD_MS        15000
#define LONG_PRESS_MS    2000
#define MIN_PRESS_MS     30
#define CSI_MAX_LEN      640
#define QUEUE_DEPTH      32

enum { STATE_IDLE = 0, STATE_SETTLE = 1, STATE_RECORDING = 2 };

typedef struct __attribute__((packed)) {
    char magic[4];               /* "EUTW" */
    uint8_t version;             /* packet format version */
    uint8_t state;               /* STATE_* at the time the CSI was received */
    uint16_t point;              /* number of short presses since boot */
    uint8_t attempt;             /* re-records of this point (long presses) */
    uint8_t rx_format;           /* rx_ctrl->cur_bb_format */
    int8_t rssi;
    int8_t noise_floor;
    uint8_t agc_gain;
    int8_t fft_gain;
    uint8_t channel;
    uint8_t rate;
    uint8_t first_word_invalid;
    uint8_t truncated;
    uint16_t csi_len;            /* bytes of CSI that follow the header */
    uint16_t sig_len;
    uint32_t boot_id;            /* random per boot: separates survey rounds */
    uint32_t seq;
    uint32_t rx_timestamp_us;    /* rx_ctrl->timestamp */
    uint32_t uptime_ms;
    uint32_t dropped;            /* records dropped because the queue was full */
    float compensate_gain;       /* from esp_csi_gain_ctrl, not applied to csi[] */
} probe_hdr_t;

typedef struct {
    probe_hdr_t hdr;
    int8_t csi[CSI_MAX_LEN];
} probe_pkt_t;

static const char *TAG = "csi_probe";

static QueueHandle_t s_queue;
static led_strip_handle_t s_led;
static uint32_t s_boot_id;
static volatile uint8_t s_state = STATE_IDLE;
static volatile uint16_t s_point;
static volatile uint8_t s_attempt;
static volatile uint32_t s_dropped;
static volatile int8_t s_last_rssi;
static volatile uint32_t s_ping_ok;
static volatile uint32_t s_ping_timeout;

static void on_ping_success(esp_ping_handle_t hdl, void *args) { s_ping_ok++; }
static void on_ping_timeout(esp_ping_handle_t hdl, void *args) { s_ping_timeout++; }

static void led_set(uint8_t r, uint8_t g, uint8_t b)
{
    /* With GRB our board showed red and green swapped (2026-10-02),
     * and led_strip 2.5 has no RGB format, so swap them here. */
    led_strip_set_pixel(s_led, 0, g, r, b);
    led_strip_refresh(s_led);
}

static void led_init(void)
{
    led_strip_config_t strip_config = {
        .strip_gpio_num = LED_GPIO,
        .max_leds = 1,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812,
        .flags.invert_out = false,
    };
    led_strip_rmt_config_t rmt_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .flags.with_dma = false,
    };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &s_led));
}

static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || memcmp(info->mac, ctx, 6)) {
        return;
    }

    static probe_pkt_t pkt;
    static uint32_t s_seq;
    const wifi_pkt_rx_ctrl_t *rx_ctrl = &info->rx_ctrl;

    uint8_t agc_gain = 0;
    int8_t fft_gain = 0;
    float compensate_gain = 1.0f;
    static uint8_t agc_baseline;
    static int8_t fft_baseline;
    esp_csi_gain_ctrl_get_rx_gain(rx_ctrl, &agc_gain, &fft_gain);
    if (s_seq < 100) {
        esp_csi_gain_ctrl_record_rx_gain(agc_gain, fft_gain);
    } else if (s_seq == 100) {
        esp_csi_gain_ctrl_get_rx_gain_baseline(&agc_baseline, &fft_baseline);
    }
    esp_csi_gain_ctrl_get_gain_compensation(&compensate_gain, agc_gain, fft_gain);

    uint16_t len = info->len > CSI_MAX_LEN ? CSI_MAX_LEN : info->len;
    probe_hdr_t *h = &pkt.hdr;
    memcpy(h->magic, "EUTW", 4);
    h->version = 1;
    h->state = s_state;
    h->point = s_point;
    h->attempt = s_attempt;
    h->rx_format = rx_ctrl->cur_bb_format;
    h->rssi = rx_ctrl->rssi;
    h->noise_floor = rx_ctrl->noise_floor;
    h->agc_gain = agc_gain;
    h->fft_gain = fft_gain;
    h->channel = rx_ctrl->channel;
    h->rate = rx_ctrl->rate;
    h->first_word_invalid = info->first_word_invalid;
    h->truncated = info->len > CSI_MAX_LEN;
    h->csi_len = len;
    h->sig_len = rx_ctrl->sig_len;
    h->boot_id = s_boot_id;
    h->seq = s_seq++;
    h->rx_timestamp_us = rx_ctrl->timestamp;
    h->uptime_ms = (uint32_t)(esp_timer_get_time() / 1000);
    h->dropped = s_dropped;
    h->compensate_gain = compensate_gain;
    memcpy(pkt.csi, info->buf, len);
    s_last_rssi = h->rssi;

    if (xQueueSend(s_queue, &pkt, 0) != pdTRUE) {
        s_dropped++;
    }
}

static uint8_t s_bssid[6];

static void promisc_rx_cb(void *buf, wifi_promiscuous_pkt_type_t type)
{
    const wifi_promiscuous_pkt_t *frame = buf;
    const wifi_pkt_rx_ctrl_t *rx_ctrl = &frame->rx_ctrl;
    if (rx_ctrl->sig_len < 24 || memcmp(frame->payload + 10, s_bssid, 6)) {
        return; /* addr2 (transmitter) must be our access point */
    }
    static probe_pkt_t pkt;
    static uint32_t s_seq;
    probe_hdr_t *h = &pkt.hdr;
    memset(h, 0, sizeof(*h));
    memcpy(h->magic, "EUTW", 4);
    h->version = 2;
    h->state = s_state;
    h->point = s_point;
    h->attempt = s_attempt;
    h->rx_format = rx_ctrl->cur_bb_format;
    h->rssi = rx_ctrl->rssi;
    h->noise_floor = rx_ctrl->noise_floor;
    h->channel = rx_ctrl->channel;
    h->rate = rx_ctrl->rate;
    h->first_word_invalid = (uint8_t)type;
    h->sig_len = rx_ctrl->sig_len;
    h->boot_id = s_boot_id;
    h->seq = s_seq++;
    h->rx_timestamp_us = rx_ctrl->timestamp;
    h->uptime_ms = (uint32_t)(esp_timer_get_time() / 1000);
    h->dropped = s_dropped;
    s_last_rssi = h->rssi;
    if (xQueueSend(s_queue, &pkt, 0) != pdTRUE) {
        s_dropped++;
    }
}

static void promisc_rssi_init(void)
{
    wifi_ap_record_t ap = {0};
    ESP_ERROR_CHECK(esp_wifi_sta_get_ap_info(&ap));
    memcpy(s_bssid, ap.bssid, 6);
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA,
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(promisc_rx_cb));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    ESP_LOGI(TAG, "promiscuous RSSI capture for frames from " MACSTR, MAC2STR(s_bssid));
}

static void wifi_csi_init(void)
{
    wifi_csi_config_t csi_config = {
        .enable                 = true,
        .acquire_csi_legacy     = true,
        .acquire_csi_ht20       = true,
        .acquire_csi_ht40       = true,
        .acquire_csi_su         = false,
        .acquire_csi_mu         = false,
        .acquire_csi_dcm        = false,
        .acquire_csi_beamformed = false,
        .acquire_csi_he_stbc    = 2,
        .val_scale_cfg          = false,
        .dump_ack_en            = false,
        .reserved               = false
    };
    static wifi_ap_record_t s_ap_info = {0};
    ESP_ERROR_CHECK(esp_wifi_sta_get_ap_info(&s_ap_info));
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, s_ap_info.bssid));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

static void ping_router_start(void)
{
    static esp_ping_handle_t ping_handle;
    esp_ping_config_t ping_config = ESP_PING_DEFAULT_CONFIG();
    ping_config.count = 0;
    ping_config.interval_ms = 1000 / PING_HZ;
    ping_config.task_stack_size = 3072;
    ping_config.data_size = 1;

    esp_netif_ip_info_t local_ip;
    esp_netif_get_ip_info(esp_netif_get_handle_from_ifkey("WIFI_STA_DEF"), &local_ip);
    ESP_LOGI(TAG, "probe ip " IPSTR ", gateway " IPSTR, IP2STR(&local_ip.ip), IP2STR(&local_ip.gw));
    if (strlen(PING_TARGET) > 0) {
        inet_pton(AF_INET, PING_TARGET, &ping_config.target_addr.u_addr.ip4.addr);
        ESP_LOGI(TAG, "pinging %s instead of the gateway", PING_TARGET);
    } else {
        ping_config.target_addr.u_addr.ip4.addr = ip4_addr_get_u32(&local_ip.gw);
    }
    ping_config.target_addr.type = ESP_IPADDR_TYPE_V4;

    esp_ping_callbacks_t cbs = {
        .on_ping_success = on_ping_success,
        .on_ping_timeout = on_ping_timeout,
    };
    ESP_ERROR_CHECK(esp_ping_new_session(&ping_config, &cbs, &ping_handle));
    ESP_ERROR_CHECK(esp_ping_start(ping_handle));
}

static void sender_task(void *arg)
{
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    struct sockaddr_in dest = {
        .sin_family = AF_INET,
        .sin_port = htons(TARGET_PORT),
    };
    inet_pton(AF_INET, TARGET_IP, &dest.sin_addr);

    static probe_pkt_t pkt;
    uint32_t sent = 0;
    uint32_t send_errors = 0;
    int64_t next_log = esp_timer_get_time() + 1000000;
    for (;;) {
        if (xQueueReceive(s_queue, &pkt, pdMS_TO_TICKS(200)) == pdTRUE) {
            size_t size = sizeof(probe_hdr_t) + pkt.hdr.csi_len;
            if (sendto(sock, &pkt, size, 0, (struct sockaddr *)&dest, sizeof(dest)) < 0) {
                send_errors++;
            } else {
                sent++;
            }
        }
        if (esp_timer_get_time() >= next_log) {
            next_log += 1000000;
            ESP_LOGI(TAG, "state %d point %u attempt %u | sent/s %lu rssi %d dropped %lu send_err %lu | ping ok %lu timeout %lu",
                     s_state, s_point, s_attempt, (unsigned long)sent, s_last_rssi,
                     (unsigned long)s_dropped, (unsigned long)send_errors,
                     (unsigned long)s_ping_ok, (unsigned long)s_ping_timeout);
            sent = 0;
        }
    }
}

static void show_state(uint8_t state)
{
    switch (state) {
    case STATE_SETTLE:    led_set(40, 30, 0); break;
    case STATE_RECORDING: led_set(50, 0, 0);  break;
    default:              led_set(0, 30, 0);  break;
    }
}

static void control_task(void *arg)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));

    bool was_pressed = false;
    bool long_shown = false;
    int64_t press_start = 0;
    int64_t phase_end = 0;
    uint8_t shown = 0xFF;

    for (;;) {
        int64_t now = esp_timer_get_time() / 1000;
        bool pressed = gpio_get_level(BUTTON_GPIO) == 0;

        if (pressed && !was_pressed) {
            press_start = now;
        }
        if (pressed && s_state == STATE_IDLE && !long_shown && now - press_start >= LONG_PRESS_MS) {
            led_set(30, 0, 40);
            long_shown = true;
        }
        if (!pressed && was_pressed && s_state == STATE_IDLE) {
            int64_t held = now - press_start;
            bool start = false;
            if (held >= LONG_PRESS_MS && s_point > 0) {
                s_attempt++;
                start = true;
                ESP_LOGI(TAG, "re-record point %u (attempt %u)", s_point, s_attempt);
            } else if (held >= MIN_PRESS_MS && held < LONG_PRESS_MS) {
                s_attempt = 0;
                s_point++;
                start = true;
                ESP_LOGI(TAG, "point %u", s_point);
            }
            if (start) {
                phase_end = now + SETTLE_MS;
                s_state = STATE_SETTLE;
            }
            long_shown = false;
            shown = 0xFF;
        }
        was_pressed = pressed;

        if (s_state == STATE_SETTLE && now >= phase_end) {
            phase_end = now + RECORD_MS;
            s_state = STATE_RECORDING;
        } else if (s_state == STATE_RECORDING && now >= phase_end) {
            s_state = STATE_IDLE;
            ESP_LOGI(TAG, "point %u done", s_point);
        }

        if (!long_shown && shown != s_state) {
            show_state(s_state);
            shown = s_state;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    led_init();
    led_set(0, 0, 40);

    ESP_ERROR_CHECK(example_connect());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    s_boot_id = esp_random();
    ESP_LOGI(TAG, "boot_id %08lx, sending to %s:%d", (unsigned long)s_boot_id, TARGET_IP, TARGET_PORT);

    s_queue = xQueueCreate(QUEUE_DEPTH, sizeof(probe_pkt_t));
    xTaskCreate(sender_task, "sender", 4096, NULL, 5, NULL);
    xTaskCreate(control_task, "control", 3072, NULL, 4, NULL);

#if USE_PROMISCUOUS_RSSI
    promisc_rssi_init();
#else
    wifi_csi_init();
#endif
    ping_router_start();
}
