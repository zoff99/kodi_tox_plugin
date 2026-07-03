import sys
import os
import ctypes
import urllib.parse
import xbmc
import xbmcvfs
import xbmcaddon
import xbmcgui
import xbmcplugin
import qrcode
import time
import platform

## export ASAN_OPTIONS="halt_on_error=false,detect_leaks=0"
## export LD_LIBRARY_PATH=/storage/:$LD_LIBRARY_PATH
## LD_PRELOAD=/storage/libasan.so.8.0.0 /usr/lib/kodi/kodi.bin --standalone -fs --audio-backend=alsa+pulseaudio

## break toxav/codecs/h264/codec.c:809


## #####################
##
##
DEBUG_MODE = False
##
##
## #####################


def load_native_library():

    addon_dir = os.path.dirname(os.path.abspath(__file__))
    xbmc.log(f"[plugin.video.koditox] trying to load native library")

    if sys.platform.startswith('win'):
        xbmc.log("[plugin.video.koditox] Detected Environment: Windows", xbmc.LOGINFO)
        lib_name = "koditox.dll"
    elif sys.platform.startswith('darwin'):
        machine = platform.machine().lower()
        if "arm" in machine or "aarch64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: MacOS arm64", xbmc.LOGINFO)
            lib_name = "koditox_arm64.dylib"
        xbmc.log("[plugin.video.koditox] Detected Environment: MacOS x86_64", xbmc.LOGINFO)
        lib_name = "koditox.dylib"
    elif sys.platform.startswith('linux'):
        machine = platform.machine().lower()
        # Check for Raspberry Pi 64-bit / Android 64-bit ARM
        if "aarch64" in machine or "arm64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux ARM 64-bit (Raspberry Pi)", xbmc.LOGINFO)
            lib_name = "libkoditox_arm64.so"
        # Check for standard Intel/AMD Linux computers
        elif "x86_64" in machine or "amd64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux Desktop/Server x86_64", xbmc.LOGINFO)
            lib_name = "libkoditox_x86_64.so"
        # Fallback for older 32-bit Raspberry Pi setups
        elif "arm" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux ARM 32-bit (Legacy RPi)", xbmc.LOGINFO)
            lib_name="libkoditox_arm32.so"

    lib_path = os.path.join(addon_dir, 'resources', 'lib', lib_name)
    xbmc.log(f"[Koditox Native] Target path evaluated to: {lib_path}", xbmc.LOGINFO)

    if not os.path.exists(lib_path):
        xbmc.log(f"[Koditox Native] CRITICAL: Binary file missing at path!", xbmc.LOGFATAL)
        return None

    try:
        # On Linux/CoreELEC, RTLD_GLOBAL helps resolve deep internal symbols
        my_c_library = ctypes.CDLL(lib_path, ctypes.RTLD_GLOBAL)
        xbmc.log("[Koditox Native] SUCCESS: Library loaded cleanly.", xbmc.LOGINFO)
        return my_c_library

    except OSError as os_err:
        error_msg = str(os_err)
        xbmc.log(f"[Koditox Native] OS ERROR DETECTED: {error_msg}", xbmc.LOGERROR)
        
        # Architecture detection check
        if "wrong elf class" in error_msg.lower():
            xbmc.log("[Koditox Native] DIAGNOSIS: Architecture Mismatch! The binary binary architecture "
                     "does not match your device processor (e.g., trying to run x86 on ARM).", xbmc.LOGFATAL)
        
        # Missing system library check
        elif "cannot open shared object file" in error_msg.lower():
            xbmc.log("[Koditox Native] DIAGNOSIS: Missing System Dependencies! This binary requires a system "
                     "library file (.so) that your operating system image does not include.", xbmc.LOGFATAL)
            
        return None


def get_native_hex_string(native_lib, profile_dir_path):
    try:
        native_lib.init.restype = ctypes.c_char_p
        native_lib.init.argtypes = [ctypes.c_char_p]

        profile_dir_bytes = profile_dir_path.encode('utf-8')
        hex_bytes = native_lib.init(profile_dir_bytes)
        return hex_bytes.decode('utf-8')
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Native initialization error: {str(e)}", xbmc.LOGERROR)
        return "error_loading_native_lib"

def get_profile_path():
    addon_profile_dir = xbmcaddon.Addon().getAddonInfo('profile')
    profile_path = xbmcvfs.translatePath(addon_profile_dir)
    if not os.path.exists(profile_path):
        os.makedirs(profile_path, exist_ok=True)
    return profile_path

def build_main_menu(handle, base_url, native_lib, profile_path):
    hex_string = get_native_hex_string(native_lib, profile_path)
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(hex_string)
    xbmc.log(f"[plugin.video.koditox] ToxID: {hex_string}", xbmc.LOGINFO)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    qr_image_path = os.path.join(profile_path, 'qrcode.png')
    img.save(qr_image_path)
    
    qr_item = xbmcgui.ListItem(label=f"Show Hex QR: {hex_string}")
    qr_item.setArt({'thumb': qr_image_path, 'icon': qr_image_path, 'poster': qr_image_path})
    qr_url = f"executebuiltin(ShowPicture({qr_image_path}))"
    xbmcplugin.addDirectoryItem(handle, url=qr_url, listitem=qr_item, isFolder=False)
    
    start_item = xbmcgui.ListItem(label="Start Tox")
    start_url = f"{base_url}?action=start"
    xbmcplugin.addDirectoryItem(handle, url=start_url, listitem=start_item, isFolder=False)

    # List of frame rates to generate
    fps_options = [30, 25, 20]

    for fps in fps_options:
        # 1. Create the item with dynamic labels
        label_text = f"Watch Tox Video Stream - {fps} fps only"
        video_item = xbmcgui.ListItem(label=label_text)

        # 2. Set the metadata tags
        video_tag = video_item.getVideoInfoTag()
        video_tag.setTitle(f"Tox 1080p Live Stream ({fps} fps)")
        video_tag.setGenres(["Live Communication"])
        video_tag.setPlot(f"Connects directly to the raw 1080p hardware-accelerated video pipeline at {fps} fps.")
        video_tag.setMediaType("video")

        # 3. Configure playback properties
        video_item.setProperty('IsPlayable', 'true')

        # 4. Build the URL with two parameters
        video_url = f"{base_url}?action=play_video&fps={fps}"

        # 5. Add to the Kodi directory
        xbmcplugin.addDirectoryItem(handle, url=video_url, listitem=video_item, isFolder=False)


    # video only mode. without re-encoding video and accepts any resolution and any FPS
    label_text = f"Watch Tox Video Stream - Video only - any fps"
    video_item = xbmcgui.ListItem(label=label_text)
    video_tag = video_item.getVideoInfoTag()
    video_tag.setTitle(f"Tox 1080p Live Stream (Video only)")
    video_tag.setGenres(["Live Communication"])
    video_tag.setPlot(f"Connects directly to the raw 1080p hardware-accelerated video pipeline. No Audio.")
    video_tag.setMediaType("video")
    video_item.setProperty('IsPlayable', 'true')
    video_url = f"{base_url}?action=play_video&vonly=true"
    xbmcplugin.addDirectoryItem(handle, url=video_url, listitem=video_item, isFolder=False)


    stop_item = xbmcgui.ListItem(label="Stop Tox")
    stop_url = f"{base_url}?action=stop"
    xbmcplugin.addDirectoryItem(handle, url=stop_url, listitem=stop_item, isFolder=False)
    
    xbmcplugin.endOfDirectory(handle)

def start_tox(native_lib, profile_path):
    try:
        get_native_hex_string(native_lib, profile_path)
        
        native_lib.start_tox_service.restype = ctypes.c_int
        status = native_lib.start_tox_service()
        
        msg = "Tox loop started." if status >= 0 else "Thread initialization failed."
        xbmcgui.Dialog().notification("KodiTox", msg, xbmcgui.NOTIFICATION_INFO, 3000)
    except Exception as e:
        xbmcgui.Dialog().notification("KodiTox", "Crash while running thread.", xbmcgui.NOTIFICATION_ERROR, 3000)
        xbmc.log(f"[plugin.video.koditox] Thread function failure: {str(e)}", xbmc.LOGERROR)

def stop_tox(native_lib):
    try:
        native_lib.stop_tox_service.restype = ctypes.c_int
        native_lib.stop_tox_service()
        xbmcgui.Dialog().notification("KodiTox", "Loop stopped and Tox destroyed.", xbmcgui.NOTIFICATION_INFO, 3000)
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Cleanup function failure: {str(e)}", xbmc.LOGERROR)










import socket
import threading
import errno
import time

# Global control event to signal the proxy thread to stop
stop_proxy_event = threading.Event()

def run_audio_proxy_engine(c_input_port=28889, ffmpeg_output_port=28899):
    """Intercepts active C stream frames and proxies them cleanly, featuring inbound packet proof logging."""
    
    stop_proxy_event.clear()

    def proxy_worker():
        try:
            # 1. Open the listening port to capture your unmodified C code data
            listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listen_sock.bind(('127.0.0.1', c_input_port))
            listen_sock.settimeout(0.5) 
            
            # 2. Open the forwarding client socket headed down to FFmpeg
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            xbmc.log(f"[plugin.video.koditox-proxy] Proxy active. Listening for C data on {c_input_port} -> forwarding to {ffmpeg_output_port}", xbmc.LOGINFO)
            
            rejection_count = 0
            inbound_packet_count = 0
            total_bytes_received = 0
            
            # 3. LIVE TRANS-FORWARD LOOP
            while not stop_proxy_event.is_set():
                try:
                    data, addr = listen_sock.recvfrom(65535)
                    if data:
                        # --- DATA PROOF LOGGING FEATURES ---
                        inbound_packet_count += 1
                        data_len = len(data)
                        total_bytes_received += data_len
                        
                        # Throttled logging: Prints data metrics exactly once every 50 packets (~1 second intervals)
                        #if inbound_packet_count % 50 == 0:
                        #    xbmc.log(
                        #        f"[plugin.video.koditox-proxy] DATA_PROOF SUCCESS: Packet #{inbound_packet_count} received from C code "
                        #        f"at address {addr}. Frame Size: {data_len} bytes. Total Volume Recv: {total_bytes_received} bytes.",
                        #        xbmc.LOGINFO
                        #    )
                        ## -----------------------------------

                        try:
                            send_sock.sendto(data, ('127.0.0.1', ffmpeg_output_port))
                        except socket.error as e:
                            rejection_count += 1
                            err_name = errno.errorcode.get(e.errno, "UNKNOWN_ERROR")
                            # Throttled rejection logging to prevent spam
                            if rejection_count % 50 == 0 or rejection_count == 1:
                                xbmc.log(
                                    f"[plugin.video.koditox-proxy] Rejection #{rejection_count}: [{err_name} (Code {e.errno})] "
                                    f"Port {ffmpeg_output_port} refused packet. FFmpeg is still initializing video stream...",
                                    xbmc.LOGDEBUG
                                )
                except socket.timeout:
                    continue
                        
            xbmc.log("[plugin.video.koditox-proxy] Proxy thread loop flag signaled stop.", xbmc.LOGINFO)
            
        except Exception as e:
            xbmc.log(f"[plugin.video.koditox-proxy] Proxy critical error: {str(e)}", xbmc.LOGERROR)
        finally:
            listen_sock.close()
            send_sock.close()
            xbmc.log("[plugin.video.koditox-proxy] Proxy sockets closed cleanly. Thread destroyed.", xbmc.LOGINFO)

    t = threading.Thread(target=proxy_worker)
    t.daemon = True
    t.start()





















# https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz
# /storage/ffmpeg-7.0.2-arm64-static/ffmpeg




import os
import stat
import subprocess
import threading
import xbmc
import xbmcgui
import xbmcplugin



ffmpeg_process = None
ffmpeg_audio_process = None

def get_platform_binary_name():
    """
    Detects the precise hardware instruction set and operating system
    to deliver the exact matched ffmpeg binary name.
    """
    if sys.platform.startswith('win'):
        xbmc.log("[plugin.video.koditox] Detected Environment: Windows", xbmc.LOGINFO)
        return "ffmpeg_win_x64.exe"
    elif sys.platform.startswith('darwin'):
        machine = platform.machine().lower()
        if "arm" in machine or "aarch64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: MacOS arm64", xbmc.LOGINFO)
            return "ffmpeg_mac_arm64"
        xbmc.log("[plugin.video.koditox] Detected Environment: MacOS x86_64", xbmc.LOGINFO)
        return "ffmpeg_mac_x86_64"
    elif sys.platform.startswith('linux'):
        machine = platform.machine().lower()
        
        # Check for Raspberry Pi 64-bit / Android 64-bit ARM
        if "aarch64" in machine or "arm64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux ARM 64-bit (Raspberry Pi)", xbmc.LOGINFO)
            return "ffmpeg_linux_arm64"
            
        # Check for standard Intel/AMD Linux computers
        elif "x86_64" in machine or "amd64" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux Desktop/Server x86_64", xbmc.LOGINFO)
            return "ffmpeg_linux_x86_64"
            
        # Fallback for older 32-bit Raspberry Pi setups
        elif "arm" in machine:
            xbmc.log("[plugin.video.koditox] Detected Environment: Linux ARM 32-bit (Legacy RPi)", xbmc.LOGINFO)
            return "ffmpeg_linux_arm32"

    return None

def run_ffmpeg_multiplexer(fps_from_tox='30', vonly='false'):
    global ffmpeg_process, ffmpeg_audio_process
    
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    binary_name = get_platform_binary_name()
    
    if not binary_name:
        return False
        
    ffmpeg_bin = os.path.join(addon_dir, 'bin', binary_name)
    
    # Ensure execution permissions on Linux/RPi
    if not sys.platform.startswith('win') and os.path.exists(ffmpeg_bin):
        try:
            st = os.stat(ffmpeg_bin)
            os.chmod(ffmpeg_bin, st.st_mode | stat.S_IEXEC)
        except:
            pass

    # Process Creation Flags across platforms to prevent hanging console windows or zombies
    creation_flags = 0
    if sys.platform.startswith('win'):
        # CREATE_NO_WINDOW = 0x08000000 (Prevents command prompt popups)
        creation_flags = 0x08000000



## -recast_media ??
## -isync input_index (input) ??

# kodi-send --action="ActivateWindow(Videos, plugin://plugin.video.koditox/)"
# kodi-send --action="RunPlugin(plugin://plugin.video.koditox/?action=start)"
# kodi-send --action="RunPlugin(plugin://plugin.video.koditox/?action=play_video)"
# kodi-send --action="RunPlugin(plugin://plugin.video.koditox/?action=stop)"


    if DEBUG_MODE == False:
        xbmc.log("[plugin.video.koditox] truncating native log file", xbmc.LOGINFO)
        # Truncate the native log file to 0 bytes before starting the stream
        try:
            with open("/tmp/koditox.log", "w"):
                pass
        except IOError:
            pass  # Fails silently if the file or directory does not exist


    if vonly=='true':
        video_cmd = [
            ffmpeg_bin,
        ]

        if DEBUG_MODE:
            xbmc.log("[plugin.video.koditox] setting debug mode ffmpeg flags", xbmc.LOGINFO)
            video_cmd.extend([
                "-v", "debug",
                "-debug_ts",
            ])
        else:
            # Optional: set a quieter log level when not debugging
            video_cmd.extend([
                "-v", "error",
            ])

        video_cmd.extend([
            "-y",
            "-re",
            "-fflags", "nobuffer+genpts+igndts",
            "-f", "h264", 
            "-i", "udp://127.0.0.1:28888?listen=1&overrun_nonfatal=1&buffer_size=524288&reuse=1&timeout=500000",
            "-map", "0:v", 
            "-c:v", "copy",       
            "-an",  # Keep audio entirely deactivated here to prevent the -22 graph crash
            "-f", "mpegts",
            "-mpegts_flags", "resend_headers",
            "-metadata", "service_provider=Tox", "-metadata", "service_name=Live",     
            "-fflags", "nobuffer+flush_packets", "-flush_packets", "1",
            "udp://127.0.0.1:28890?pkt_size=1316&overrun_nonfatal=1"
        ])
    else:

        video_cmd = [
            ffmpeg_bin,
            # Global Flags
        ]

        if DEBUG_MODE:
            xbmc.log("[plugin.video.koditox] setting debug mode ffmpeg flags", xbmc.LOGINFO)
            video_cmd.extend([
                "-v", "debug",
                "-debug_ts",
            ])
        else:
            # Optional: set a quieter log level when not debugging
            video_cmd.extend([
                "-v", "error",
            ])

        video_cmd.extend([
            "-y",
            "-max_error_rate", "1.0",
            "-fflags", "nobuffer+genpts",
            "-ignore_unknown",
            "-frame_drop_threshold", "9999999999",
            "-reinit_filter", "0",                         # Tells the filter complex to survive dead inputs

    ##        "-max_muxing_queue_size", "10000",

            # Video Input Block (Input 0)
            "-f", "h264",
            "-fflags", "+genpts+igndts",
            "-r", fps_from_tox,
            "-discard", "nokey",
    #        "-readrate_catchup", "5",
    ###        "-readrate", "5",
    ###        "-readrate_initial_burst", "100",
            "-use_wallclock_as_timestamps", "1",
            "-thread_queue_size", "16",
            "-i", "udp://127.0.0.1:28888?listen=1&overrun_nonfatal=1&fifo_size=2000000&buffer_size=51231230&reuse=1&timeout=800000",

            # Audio Input Block 1: Silence Baseline (Input 1) -> EXACT CONFIG COMPATIBLE
            "-f", "lavfi",
            "-thread_queue_size", "512",
            # SWAPPED: sine filter replaced with anullsrc to provide a silent, continuous timeline driver
            "-i", "anullsrc=sample_rate=48000,aformat=channel_layouts=stereo,arealtime",

            # Audio Input Block 2: Real PCM Stream (Input 2)
            "-f", "s16le", 
            "-ar", "48000", 
            "-ac", "2", 
            "-probesize", "32",
            "-analyzeduration", "0",
            "-use_wallclock_as_timestamps", "1", 
            "-thread_queue_size", "512",
            "-i", "udp://127.0.0.1:28899?listen=1&overrun_nonfatal=1&buffer_size=1048576&reuse=1&timeout=10000",

            # Maps
            "-map", "0:v",
            "-map", "[a]",

            # Video Output Processing Configuration
            "-c:v", "libx264",                    
            "-preset", "ultrafast",               
            "-tune", "zerolatency",               
            "-g", fps_from_tox,
            "-crf", "23",                         

            # Audio Output Processing Configuration -> STRIPPED TIMESTAMP BREAKAGE
            "-c:a", "aac",        
            "-ac", "2",
            "-filter_complex", (
                "[2:a]asetpts=N,arealtime,aresample=async=1:min_hard_comp=0.010000[livepcm];"
                "[1:a][livepcm]amix=inputs=2:duration=first:weights=1 1:dropout_transition=0:normalize=0[mixed];"
                "[mixed]aresample=async=1:min_hard_comp=0.100000[a]"
            ),

            # Output Muxing Stream Engine
            "-f", "mpegts",
            "-muxdelay", "2.0",
            "-mpegts_copyts", "0",
            "-mpegts_flags", "resend_headers+initial_discontinuity",
            "-metadata", "service_provider=Tox",
            "-metadata", "service_name=Live",     
            "-fflags", "nobuffer+flush_packets",
            "-flush_packets", "1",
            "udp://127.0.0.1:28890?pkt_size=1316&overrun_nonfatal=1"
        ])

    
    try:
        xbmc.log("[plugin.video.koditox] Spawning isolated dual-engine pipelines...", xbmc.LOGINFO)

        if vonly=='false':
            run_audio_proxy_engine(c_input_port=28889, ffmpeg_output_port=28899)

        # Launch Video Node
        ffmpeg_process = subprocess.Popen(
            video_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.PIPE, close_fds=True, creationflags=creation_flags
        )

        # FIXED: Immediately drain stderr in a thread to prevent OS buffer deadlock
        def log_ffmpeg_errors():
            while ffmpeg_process:
                line = ffmpeg_process.stderr.readline()
                if not line:
                    xbmc.log(f"[plugin.video.koditox-ffmpeg] exiting ffmpeg stderr logging loop", xbmc.LOGINFO)
                    break
                xbmc.log(f"[plugin.video.koditox-ffmpeg] {line.decode('utf-8', errors='ignore').strip()}", xbmc.LOGINFO)
                    
        diag_thread = threading.Thread(target=log_ffmpeg_errors, daemon=True)
        diag_thread.start()
        
        
        xbmc.sleep(800)
        
        if ffmpeg_process.poll() is not None:
            return False

        # --- NEW IMPLEMENTATION: Save PIDs to allow cross-thread absolute termination ---
        save_engine_pids(ffmpeg_process.pid, None)
        # ---------------------------------------------------------------------------------


        return True
        
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Process spawn exception: {str(e)}", xbmc.LOGERROR)
        return False


tox_monitor = None


def play_video(handle, native_lib, fps='30', vonly='false'):
    global ffmpeg_process, ffmpeg_audio_process, tox_monitor
    list_item = xbmcgui.ListItem("Tox Video Call")
    
    try:
        # --- NEW IMPLEMENTATION: Pure process termination by PID baseline ---
        hard_kill_tracked_pids()
        ffmpeg_process = None
        ffmpeg_audio_process = None
        # ---------------------------------------------------------------------

        if ffmpeg_process is None:
            if not run_ffmpeg_multiplexer(fps, vonly):
                raise RuntimeError("FFmpeg engines failed to initialize loop ports.")
            xbmc.sleep(800) 

        if vonly=='true':
            ff_opts = "-f mpegts -probesize 16384 -analyzeduration 100000 -fflags nobuffer+genpts+igndts -flags low_delay -an"
            stream_url = (
                f"udp://127.0.0.1:28890?overrun_nonfatal=1&fifo_size=50000"
                f"|ffmpegoptions={ff_opts}"
            )
            xbmc.log(f"[plugin.video.koditox] Connecting to isolated multi-source engine link: {stream_url}", xbmc.LOGINFO)

            list_item.setPath(stream_url)
            
            video_tag = list_item.getVideoInfoTag()
            video_tag.setTitle("Tox Live Stream")
            video_tag.setMediaType("video")
            
            list_item.setProperty('IsPlayable', 'true')
            list_item.setProperty('mimetype', 'video/mp2t') 
            list_item.setProperty('isLive', 'true')
            
            list_item.setProperty('inputstream', 'inputstream.ffmpegdirect')
            list_item.setProperty('inputstream.ffmpegdirect.stream_mode', 'default')
            list_item.setProperty('inputstream.ffmpegdirect.is_realtime_stream', 'true')
            list_item.setProperty('inputstream.ffmpegdirect.mimic_targetduration', '0')
            list_item.setProperty('inputstream.ffmpegdirect.open_mode', 'ffmpeg')
            
            list_item.setProperty('inputstream.ffmpegdirect.has_audio', 'false')

            list_item.setProperty('force_direct_rendering', 'true')
            list_item.setProperty('realtime', 'true')

        else:
            ff_opts = "-f mpegts -probesize 2000000 -analyzeduration 2000000 -fflags nobuffer+genpts -flags low_delay"
            stream_url = (
                f"udp://127.0.0.1:28890?overrun_nonfatal=1&fifo_size=1500000"
                f"|ffmpegoptions={ff_opts}"
            )
            xbmc.log(f"[plugin.video.koditox] Connecting to isolated multi-source engine link: {stream_url}", xbmc.LOGINFO)

            list_item.setPath(stream_url)
            
            video_tag = list_item.getVideoInfoTag()
            video_tag.setTitle("Tox Live Stream")
            video_tag.setMediaType("video")
            
            list_item.setProperty('IsPlayable', 'true')
            list_item.setProperty('mimetype', 'video/mp2t') 
            list_item.setProperty('isLive', 'true')
            
            list_item.setProperty('inputstream', 'inputstream.ffmpegdirect')
            list_item.setProperty('inputstream.ffmpegdirect.stream_mode', 'default')
            list_item.setProperty('inputstream.ffmpegdirect.is_realtime_stream', 'true')
            list_item.setProperty('inputstream.ffmpegdirect.mimic_targetduration', '0')
            list_item.setProperty('inputstream.ffmpegdirect.open_mode', 'ffmpeg')
            
            ## AUDIO ## list_item.setProperty('inputstream.ffmpegdirect.audio_sw_sync', 'true')
            list_item.setProperty('inputstream.ffmpegdirect.has_audio', 'true')

            list_item.setProperty('force_direct_rendering', 'true')
            list_item.setProperty('realtime', 'true')




        # --- NEW CODE: Initialize the callback monitor & overlay UI ---
        if tox_monitor is not None:
            tox_monitor.cleanup()
        tox_monitor = ToxVideoMonitor(native_lib)
        # -------------------------------------------------------------
        
        xbmcplugin.setResolvedUrl(handle, True, list_item)

        xbmc.log("[plugin.video.koditox] Stream resolved. Entering script-keepalive block.", xbmc.LOGINFO)

        # Give Kodi up to 10 seconds to start playback, or break early if abort is requested
        monitor = xbmc.Monitor()
        timeout = 0
        while not tox_monitor.isPlaying() and not monitor.waitForAbort(1) and timeout < 10:
            timeout += 1



        # --- NEW CODE: Actively monitor process lifecycles to detect remote hangups ---
        while tox_monitor.is_running and not monitor.waitForAbort(1):
            # Check the global execution processes
            if ffmpeg_process is not None and ffmpeg_process.poll() is not None:
                xbmc.log("[plugin.video.koditox] Video engine disconnected (Remote hangup). Breaking loop.", xbmc.LOGINFO)
                break

            xbmc.sleep(500)

        # If the remote side stopped the call, explicitly tell the player to stop before hitting finally
        if tox_monitor.isPlayingVideo():
            xbmc.Player().stop()

        xbmc.log("[plugin.video.koditox] Playback ended. Releasing keepalive block.", xbmc.LOGINFO)


    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Setup execution failure: {str(e)}", xbmc.LOGERROR)

    finally:
        # =========================================================================
        # CRITICAL FIX: The finally block ALWAYS runs when the stream stops,
        # ensuring the OS kernel-level kill utility executes on the main thread.
        # =========================================================================
        xbmc.log("[plugin.video.koditox] Exiting main script context. Invoking mandatory engine purge.", xbmc.LOGINFO)
        hard_kill_tracked_pids()
        if tox_monitor:
            tox_monitor.cleanup()
            tox_monitor = None


class ToxPlaybackMonitor(xbmc.Player):
    def onPlayBackStopped(self):
        xbmc.log("[plugin.video.koditox] Playback Stopped. Invoking hard-kill sequence.", xbmc.LOGINFO)
        hard_kill_tracked_pids()

    def onPlayBackEnded(self):
        xbmc.log("[plugin.video.koditox] Playback Ended. Invoking hard-kill sequence.", xbmc.LOGINFO)
        hard_kill_tracked_pids()






import os
import signal
import xbmc
import xbmcvfs

def save_engine_pids(video_pid, audio_pid):
    """Writes active FFmpeg PIDs to a temporary file in the addon profile path."""
    profile_dir = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.koditox")
    if not os.path.exists(profile_dir):
        os.makedirs(profile_dir)
    pid_file = os.path.join(profile_dir, "ffmpeg_engines.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(f"{video_pid}")
        # Added detailed logging showing the exact target file path
        xbmc.log(f"[plugin.video.koditox] WRITING PIDs. Video: {video_pid}, Audio: {audio_pid} to target path: {pid_file}", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Failed to write PID file: {e}", xbmc.LOGERROR)

def hard_kill_tracked_pids():
    """Reads the stored PIDs and issues a kernel-level SIGKILL directly to the OS layers."""
    profile_dir = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.koditox")
    pid_file = os.path.join(profile_dir, "ffmpeg_engines.pid")

    try:
        stop_proxy_event.set()
    except:
        xbmc.log(f"[plugin.video.koditox] stopping audio proxy thread failed", xbmc.LOGINFO)

    xbmc.log(f"[plugin.video.koditox] stopping python audio udp thread", xbmc.LOGINFO)
    
    # Added logging to trace exactly where the cleanup looks for the file
    xbmc.log(f"[plugin.video.koditox] CHECKING for target PID file at path: {pid_file}", xbmc.LOGINFO)
    
    if not os.path.exists(pid_file):
        xbmc.log(f"[plugin.video.koditox] TARGET FILE NOT FOUND at path: {pid_file}", xbmc.LOGINFO)
        return

    try:
        with open(pid_file, "r") as f:
            pids = f.read().strip().split(",")
        
        xbmc.log(f"[plugin.video.koditox] READ PIDs from file: {pids}", xbmc.LOGINFO)
        
        for pid_str in pids:
            if pid_str.isdigit():
                pid = int(pid_str)
                try:
                    # Execute direct kernel kill
                    os.kill(pid, signal.SIGKILL)
                    xbmc.log(f"[plugin.video.koditox] EXECUTED target kernel SIGKILL on PID: {pid}", xbmc.LOGINFO)
                except OSError as os_err:
                    xbmc.log(f"[plugin.video.koditox] KERNEL REJECTED kill for PID {pid}. Reason: {os_err}", xbmc.LOGINFO)
                    
        if os.path.exists(pid_file):
            os.remove(pid_file)
            xbmc.log(f"[plugin.video.koditox] CLEANED UP tracking state file from storage: {pid_file}", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Error executing hard-kill tracking routine: {e}", xbmc.LOGERROR)










import xbmc
import xbmcgui

class ToxOSDOverlay(xbmcgui.WindowDialog):
    def __init__(self):
        super().__init__()
        
        # Color configuration
        COLOR_WHITE = '0xFFFFFFFF'
        COLOR_BLACK = '0xFF000000'
        
        # Coordinates (Slightly more padding to prevent text-clipping)
        x1, y1 = 15, 20  
        x2, y2 = 15, 35  
        label_w = 600
        label_h = 20
        chosen_font = 'font10' 
        
        # --- LINE 1 GENERATION ---
        # 4 cardinal directions at exactly 1-pixel thickness for a clean boundary
        self.shadows_line1 = [
            xbmcgui.ControlLabel(x1-1, y1,   label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK), # Left
            xbmcgui.ControlLabel(x1+1, y1,   label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK), # Right
            xbmcgui.ControlLabel(x1,   y1-1, label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK), # Up
            xbmcgui.ControlLabel(x1,   y1+1, label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK)  # Down
        ]
        for outline in self.shadows_line1:
            self.addControl(outline)
            
        self.label_line1 = xbmcgui.ControlLabel(x1, y1, label_w, label_h, "", font=chosen_font, textColor=COLOR_WHITE)
        self.addControl(self.label_line1)
        
        # --- LINE 2 GENERATION ---
        self.shadows_line2 = [
            xbmcgui.ControlLabel(x2-1, y2,   label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK),
            xbmcgui.ControlLabel(x2+1, y2,   label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK),
            xbmcgui.ControlLabel(x2,   y2-1, label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK),
            xbmcgui.ControlLabel(x2,   y2+1, label_w, label_h, "", font=chosen_font, textColor=COLOR_BLACK)
        ]
        for outline in self.shadows_line2:
            self.addControl(outline)
            
        self.label_line2 = xbmcgui.ControlLabel(x2, y2, label_w, label_h, "", font=chosen_font, textColor=COLOR_WHITE)
        self.addControl(self.label_line2)
        
    def update_line1(self, text):
        for outline in self.shadows_line1:
            outline.setLabel(text)
        self.label_line1.setLabel(text)

    def update_line2(self, text):
        for outline in self.shadows_line2:
            outline.setLabel(text)
        self.label_line2.setLabel(text)



class ToxVideoMonitor(xbmc.Player):
    def __init__(self, native_lib):
        super().__init__()
        self.native_lib = native_lib
        self.is_running = True
        self.osd = None
        self.poll_thread = None
        self.kodi_monitor = xbmc.Monitor()
        
        # Configure the ctypes function signature for the polling bridge
        self.native_lib.get_latest_telemetry.argtypes = [
            ctypes.POINTER(ctypes.c_uint32), # Pointer to friend_number
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int64),
            ctypes.c_void_p
        ]

        self.native_lib.get_latest_telemetry.restype = ctypes.c_int # Returns 0 or 1

    def onAVStarted(self):
        xbmc.log("[plugin.video.koditox] Video active. Initializing OSD and starting polling loop.", xbmc.LOGINFO)
        xbmc.sleep(500)
        
        try:
            self.osd = ToxOSDOverlay()
            self.osd.show()
            
            # Spawn the polling loop thread inside Python's safe territory
            if self.poll_thread is None:
                self.poll_thread = threading.Thread(target=self._telemetry_poll_loop)
                self.poll_thread.daemon = True
                self.poll_thread.start()
        except Exception as e:
            xbmc.log(f"[plugin.video.koditox] Failed to open overlay layer: {e}", xbmc.LOGERROR)

    def _telemetry_poll_loop(self):
        xbmc.log("[plugin.video.koditox] Telemetry poll thread started.", xbmc.LOGINFO)
        
        # Create ctypes container variables to receive values from C
        friend_number = ctypes.c_uint32(0)
        toxav_decoder_bitrate = ctypes.c_int64(0)
        toxav_video_width = ctypes.c_uint32(0)
        toxav_video_height = ctypes.c_uint32(0)
        toxav_network_roundtrip_ms = ctypes.c_int64(0)
        toxav_play_buffer_entries = ctypes.c_int32(0)
        toxav_incoming_fps = ctypes.c_int64(0)
        string_buffer = ctypes.create_string_buffer(200)

        while self.is_running and not self.kodi_monitor.abortRequested():
            # Call into the C function passing references to our variables
            new_data_available = self.native_lib.get_latest_telemetry(
                ctypes.byref(friend_number),
                ctypes.byref(toxav_decoder_bitrate),
                ctypes.byref(toxav_video_width),
                ctypes.byref(toxav_video_height),
                ctypes.byref(toxav_network_roundtrip_ms),
                ctypes.byref(toxav_play_buffer_entries),
                ctypes.byref(toxav_incoming_fps),
                ctypes.cast(string_buffer, ctypes.c_void_p)
            )
            
            # If the C layer returned 1, update the visible text layout
            ## xbmc.log(f"[plugin.video.koditox] Polled new metrics", xbmc.LOGINFO)
            native_string = string_buffer.value.decode('utf-8', errors='ignore')
            if self.osd is not None:
                    status_text = f"FPS: {toxav_incoming_fps.value} BR: {toxav_decoder_bitrate.value} RES: {toxav_video_width.value}x{toxav_video_height.value}"
                    self.osd.update_line1(status_text)                        
                    # status_text = f"RTT: {toxav_network_roundtrip_ms.value} BUF FRAMES: {toxav_play_buffer_entries.value}"
                    status_text = f"{native_string}"
                    self.osd.update_line2(status_text)

            # Thread-safe breakable sleep pattern split into small intervals
            for _ in range(10):
                if not self.is_running or self.kodi_monitor.abortRequested():
                    break
                xbmc.sleep(100)

    def onPlayBackStopped(self):
        xbmc.log("[plugin.video.koditox] Stream playback stopped by user interaction.", xbmc.LOGINFO)
        hard_kill_tracked_pids()
        self.cleanup()

    def onPlayBackEnded(self):
        xbmc.log("[plugin.video.koditox] Stream playback ended by remote stream closure.", xbmc.LOGINFO)
        hard_kill_tracked_pids()
        self.cleanup()

    def cleanup(self):
        xbmc.log("[plugin.video.koditox] Cleaning up monitor and killing poll loop.", xbmc.LOGINFO)
        self.is_running = False
        
        if self.osd:
            try:
                self.osd.close()
            except Exception:
                pass
        self.osd = None

        if self.poll_thread and self.poll_thread.is_alive():
            try:
                self.poll_thread.join(timeout=1.0)
            except Exception:
                pass
        xbmc.log("[plugin.video.koditox] Cleanup complete.", xbmc.LOGINFO)



def run():
    base_url = sys.argv[0]
    handle = int(sys.argv[1])
    query_string = sys.argv[2]
    
    try:
        native_lib = load_native_library()
    except Exception as e:
        xbmcgui.Dialog().notification("KodiTox", "Missing runtime libraries.", xbmcgui.NOTIFICATION_ERROR, 3000)
        return

    profile_path = get_profile_path()
    params = dict(urllib.parse.parse_qsl(query_string.lstrip('?')))
    action = params.get('action')
    
    if action == 'start':
        start_tox(native_lib, profile_path)
    elif action == 'stop':
        stop_tox(native_lib)
    elif action == 'play_video':
        fps_value = params.get('fps', '30')
        video_only_mode = params.get('vonly', 'false')
        play_video(handle, native_lib, fps=fps_value, vonly=video_only_mode)
    else:
        build_main_menu(handle, base_url, native_lib, profile_path)

if __name__ == '__main__':
    run()
