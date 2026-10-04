package de.kisum.eutwin.recorder

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.wifi.WifiManager
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.ar.core.exceptions.NotYetAvailableException
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * Walk recorder: ARCore camera pose + depth, Wi-Fi RSSI of the connected network, and the
 * RSSI of every BLE advertisement, all stamped with SystemClock.elapsedRealtimeNanos().
 * Files go to /sdcard/Android/data/de.kisum.eutwin.recorder/files/<session>/.
 */
class MainActivity : Activity(), GLSurfaceView.Renderer {

    private lateinit var surface: GLSurfaceView
    private lateinit var status: TextView
    private lateinit var button: Button
    private val background = BackgroundRenderer()

    private var session: Session? = null
    private var installRequested = false
    private var viewWidth = 0
    private var viewHeight = 0

    @Volatile private var recorder: SessionRecorder? = null
    private var lastDepthNs = 0L
    private var lastStatusNs = 0L

    @Volatile private var lastWifiRssi = 0
    @Volatile private var lastBleRssi = 0
    @Volatile private var bleCount = 0
    @Volatile private var wifiChanges = 0
    @Volatile private var tracking = "-"

    /** Latest advertisement per device, for the on-screen list of the strongest senders. */
    private class Seen(val name: String, val rssi: Int, val tNs: Long, val count: Int)
    private val seen = ConcurrentHashMap<String, Seen>()

    private val pollThread = HandlerThread("wifi-poll").apply { start() }
    private val pollHandler = Handler(pollThread.looper)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        surface = GLSurfaceView(this).apply {
            preserveEGLContextOnPause = true
            setEGLContextClientVersion(2)
            setEGLConfigChooser(8, 8, 8, 8, 16, 0)
            setRenderer(this@MainActivity)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        status = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(0x99000000.toInt())
            textSize = 16f
            setPadding(24, 24, 24, 24)
        }
        button = Button(this).apply {
            text = "Start"
            textSize = 22f
            setOnClickListener { toggleRecording() }
        }
        val overlay = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(status)
        }
        val root = FrameLayout(this)
        root.addView(surface)
        root.addView(overlay, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        root.addView(button, FrameLayout.LayoutParams(-1, 220, Gravity.BOTTOM))
        setContentView(root)

        val needed = mutableListOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION)
        if (Build.VERSION.SDK_INT >= 31) needed += Manifest.permission.BLUETOOTH_SCAN
        val missing = needed.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) requestPermissions(missing.toTypedArray(), 1)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) return
        if (session == null) {
            when (ArCoreApk.getInstance().requestInstall(this, !installRequested)) {
                ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                    installRequested = true
                    return
                }
                else -> {}
            }
            session = Session(this).also { s ->
                val config = Config(s)
                config.focusMode = Config.FocusMode.AUTO
                config.depthMode = if (s.isDepthModeSupported(Config.DepthMode.AUTOMATIC))
                    Config.DepthMode.AUTOMATIC else Config.DepthMode.DISABLED
                s.configure(config)
            }
        }
        session?.resume()
        surface.onResume()
        startBle()
    }

    override fun onPause() {
        super.onPause()
        stopBle()
        surface.onPause()
        session?.pause()
    }

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        recreate()
    }

    private fun toggleRecording() {
        val r = recorder
        if (r == null) {
            val name = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val dir = File(getExternalFilesDir(null), name)
            if (session == null) return
            recorder = SessionRecorder(dir, Build.MODEL)
            bleCount = 0
            wifiChanges = 0
            startWifi()
            button.text = "Stop"
        } else {
            stopWifi()
            recorder = null
            r.close()
            button.text = "Start"
        }
    }

    // ---------------- Wi-Fi ----------------

    private val wifiManager by lazy { applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager }

    private val rssiReceiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context, intent: Intent) {
            val rssi = intent.getIntExtra(WifiManager.EXTRA_NEW_RSSI, -127)
            wifiChanges++
            recorder?.wifi(SystemClock.elapsedRealtimeNanos(), "broadcast", rssi, "", 0, 0)
        }
    }

    private val pollTask = object : Runnable {
        override fun run() {
            @Suppress("DEPRECATION")
            val info = wifiManager.connectionInfo
            if (info != null) {
                lastWifiRssi = info.rssi
                recorder?.wifi(SystemClock.elapsedRealtimeNanos(), "poll", info.rssi,
                    info.bssid ?: "", info.frequency, info.linkSpeed)
            }
            pollHandler.postDelayed(this, 100)
        }
    }

    private fun startWifi() {
        registerReceiver(rssiReceiver, IntentFilter(WifiManager.RSSI_CHANGED_ACTION))
        pollHandler.post(pollTask)
    }

    private fun stopWifi() {
        pollHandler.removeCallbacks(pollTask)
        unregisterReceiver(rssiReceiver)
    }

    // ---------------- BLE ----------------

    private val bleCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val name = result.scanRecord?.deviceName ?: ""
            if (name.startsWith(BEACON_PREFIX)) {
                lastBleRssi = result.rssi
                bleCount++
            }
            val addr = result.device.address
            val prev = seen[addr]
            seen[addr] = Seen(name.ifEmpty { prev?.name ?: "" }, result.rssi, SystemClock.elapsedRealtimeNanos(),
                (prev?.count ?: 0) + 1)
            recorder?.ble(result.timestampNanos, addr, result.rssi, name)
        }
    }

    @Suppress("MissingPermission")
    private fun startBle() {
        val scanner = (getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter?.bluetoothLeScanner
            ?: return
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .setReportDelay(0)
            .build()
        scanner.startScan(null, settings, bleCallback)
    }

    @Suppress("MissingPermission")
    private fun stopBle() {
        (getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter?.bluetoothLeScanner
            ?.stopScan(bleCallback)
    }

    // ---------------- ARCore / GL ----------------

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        background.create()
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        viewWidth = width
        viewHeight = height
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)
        val s = session ?: return
        s.setCameraTextureName(background.textureId)
        s.setDisplayGeometry(windowManager.defaultDisplay.rotation, viewWidth, viewHeight)
        val frame = try { s.update() } catch (e: Exception) { return }
        background.draw(frame)

        val now = SystemClock.elapsedRealtimeNanos()
        val camera = frame.camera
        tracking = camera.trackingState.name
        val r = recorder
        if (r != null) {
            r.pose(now, frame.timestamp, camera.trackingState, camera.pose)
            if (camera.trackingState == TrackingState.TRACKING && now - lastDepthNs > DEPTH_PERIOD_NS) {
                try {
                    frame.acquireDepthImage16Bits().use { img ->
                        r.depth(now, frame.timestamp, img, camera.pose, camera.imageIntrinsics)
                        lastDepthNs = now
                    }
                } catch (_: NotYetAvailableException) {
                }
            }
        }
        if (now - lastStatusNs > 250_000_000L) {
            lastStatusNs = now
            val p = camera.pose
            val text = buildString {
                append(if (r != null) "RECORDING  ${"%.0f".format((now - r.startNs) / 1e9)} s\n" else "ready\n")
                append("tracking: $tracking\n")
                append("pos: %.2f %.2f %.2f\n".format(p.tx(), p.ty(), p.tz()))
                append("Wi-Fi RSSI: $lastWifiRssi dBm (updates: $wifiChanges)\n")
                append("BLE $BEACON_PREFIX: $lastBleRssi dBm (packets: $bleCount)\n")
                if (r != null) append("depth frames: ${r.depthCount}\n")
                append("strongest BLE senders (last 3 s):\n")
                seen.entries.filter { now - it.value.tNs < 3_000_000_000L }
                    .sortedByDescending { it.value.rssi }.take(4)
                    .forEach { append("  ${it.value.rssi} dBm  ${it.value.name.ifEmpty { "(no name)" }}  ${it.key.takeLast(5)}  n=${it.value.count}\n") }
            }
            runOnUiThread { status.text = text }
        }
    }

    companion object {
        const val BEACON_PREFIX = "EUTWIN"
        const val DEPTH_PERIOD_NS = 330_000_000L
    }
}
