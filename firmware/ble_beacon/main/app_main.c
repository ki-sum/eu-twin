/*
 * BLE reference beacon for the EU Twin walk test.
 *
 * Sits at the router position and sends non-connectable advertisements named
 * "EUTWIN-BCN" every 20 ms at a fixed +9 dBm, so a phone can measure 2.4 GHz
 * path loss through the house without reading Wi-Fi RSSI.
 */
#include <string.h>
#include "esp_bt.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "host/ble_hs.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"

#define BEACON_NAME "EUTWIN-BCN"
#define ADV_INTERVAL_UNITS 32 /* 32 x 0.625 ms = 20 ms */

static const char *TAG = "ble_beacon";

static void start_advertising(void)
{
    uint8_t own_addr_type;
    int rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "address type error %d", rc);
        return;
    }

    struct ble_hs_adv_fields fields;
    memset(&fields, 0, sizeof(fields));
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (uint8_t *)BEACON_NAME;
    fields.name_len = strlen(BEACON_NAME);
    fields.name_is_complete = 1;
    fields.tx_pwr_lvl = 9;
    fields.tx_pwr_lvl_is_present = 1;
    rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "set fields error %d", rc);
        return;
    }

    struct ble_gap_adv_params params;
    memset(&params, 0, sizeof(params));
    params.conn_mode = BLE_GAP_CONN_MODE_NON;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    params.itvl_min = ADV_INTERVAL_UNITS;
    params.itvl_max = ADV_INTERVAL_UNITS;
    rc = ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &params, NULL, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "adv start error %d", rc);
        return;
    }
    uint8_t addr[6] = {0};
    ble_hs_id_copy_addr(own_addr_type, addr, NULL);
    ESP_LOGI(TAG, "advertising as %s, %02x:%02x:%02x:%02x:%02x:%02x, every %d ms, +9 dBm",
             BEACON_NAME, addr[5], addr[4], addr[3], addr[2], addr[1], addr[0],
             ADV_INTERVAL_UNITS * 625 / 1000);
}

static void on_sync(void)
{
    esp_err_t err = esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, ESP_PWR_LVL_P9);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "tx power set failed: %s", esp_err_to_name(err));
    }
    start_advertising();
}

static void on_reset(int reason)
{
    ESP_LOGW(TAG, "host reset, reason %d", reason);
}

static void host_task(void *param)
{
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(nimble_port_init());
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    nimble_port_freertos_init(host_task);
}
