package de.kisum.eutwin.recorder

import android.media.Image
import android.os.SystemClock
import com.google.ar.core.CameraIntrinsics
import com.google.ar.core.Pose
import com.google.ar.core.TrackingState
import java.io.BufferedWriter
import java.io.File
import java.io.FileOutputStream
import java.util.Locale

/**
 * Writes one walk to disk. All t_ns columns are SystemClock.elapsedRealtimeNanos();
 * frame_ns is ARCore's frame timestamp. Poses are ARCore camera poses (camera looks
 * down -Z, +Y up, sensor orientation), world frame gravity-aligned with +Y up.
 */
class SessionRecorder(private val dir: File, private val model: String) {
    val startNs = SystemClock.elapsedRealtimeNanos()
    var depthCount = 0
        private set

    private val depthDir = File(dir, "depth").apply { mkdirs() }
    private val poses = writer("poses.csv", "t_ns,frame_ns,tracking,tx,ty,tz,qx,qy,qz,qw")
    private val depths = writer("depth.csv", "index,t_ns,frame_ns,width,height,tx,ty,tz,qx,qy,qz,qw")
    private val wifi = writer("wifi.csv", "t_ns,source,rssi,bssid,freq_mhz,link_mbps")
    private val ble = writer("ble.csv", "t_ns,address,rssi,name")
    private var intrinsicsWritten = false

    private fun writer(name: String, header: String): BufferedWriter =
        File(dir, name).bufferedWriter().apply { write(header); newLine() }

    private fun poseCols(p: Pose) = String.format(
        Locale.US, "%.5f,%.5f,%.5f,%.6f,%.6f,%.6f,%.6f",
        p.tx(), p.ty(), p.tz(), p.qx(), p.qy(), p.qz(), p.qw()
    )

    @Synchronized
    fun pose(tNs: Long, frameNs: Long, state: TrackingState, p: Pose) {
        poses.write("$tNs,$frameNs,${state.name},${poseCols(p)}")
        poses.newLine()
    }

    @Synchronized
    fun depth(tNs: Long, frameNs: Long, img: Image, p: Pose, intr: CameraIntrinsics) {
        if (!intrinsicsWritten) writeMeta(img.width, img.height, intr)
        val plane = img.planes[0]
        val buf = plane.buffer
        val rowBytes = img.width * 2
        val out = ByteArray(rowBytes * img.height)
        for (row in 0 until img.height) {
            buf.position(row * plane.rowStride)
            buf.get(out, row * rowBytes, rowBytes)
        }
        FileOutputStream(File(depthDir, "%06d.bin".format(depthCount))).use { it.write(out) }
        depths.write("$depthCount,$tNs,$frameNs,${img.width},${img.height},${poseCols(p)}")
        depths.newLine()
        depthCount++
    }

    @Synchronized
    fun wifi(tNs: Long, source: String, rssi: Int, bssid: String, freq: Int, link: Int) {
        wifi.write("$tNs,$source,$rssi,$bssid,$freq,$link")
        wifi.newLine()
    }

    @Synchronized
    fun ble(tNs: Long, address: String, rssi: Int, name: String) {
        ble.write("$tNs,$address,$rssi,${name.replace(',', ' ')}")
        ble.newLine()
    }

    private fun writeMeta(depthW: Int, depthH: Int, intr: CameraIntrinsics) {
        val f = intr.focalLength
        val c = intr.principalPoint
        val d = intr.imageDimensions
        File(dir, "meta.json").writeText(
            """
            {
              "model": "$model",
              "start_ns": $startNs,
              "image_fx": ${f[0]}, "image_fy": ${f[1]},
              "image_cx": ${c[0]}, "image_cy": ${c[1]},
              "image_width": ${d[0]}, "image_height": ${d[1]},
              "depth_width": $depthW, "depth_height": $depthH,
              "depth_format": "uint16 little-endian millimetres, row-major"
            }
            """.trimIndent()
        )
        intrinsicsWritten = true
    }

    @Synchronized
    fun close() {
        poses.close()
        depths.close()
        wifi.close()
        ble.close()
    }
}
