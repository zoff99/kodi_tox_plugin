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



#
#    # 3. NEW: Watch Tox Video Stream Menu Item
#    video_item = xbmcgui.ListItem(label="Watch Tox Video Stream")
#    # Setting the info block tells Kodi to treat this item as an interactive video asset
#    video_item.setInfo('video', {
#        'title': 'Tox 1080p Live Stream',
#        'genre': 'Live Communication',
#        'plot': 'Connects directly to the raw 1080p hardware-accelerated video pipeline.'
#    })
#    # Tell Kodi this item will immediately play a stream rather than open another directory folder
#    video_item.setProperty('IsPlayable', 'true') 
#    video_url = f"{base_url}?action=play_video"
#    xbmcplugin.addDirectoryItem(handle, url=video_url, listitem=video_item, isFolder=False)
#

    # Watch Tox Video Stream Menu Item (Updated API)
    video_item = xbmcgui.ListItem(label="Watch Tox Video Stream")
    
    # FIX: Get the clean modern video info tag object
    video_tag = video_item.getVideoInfoTag()
    video_tag.setTitle("Tox 1080p Live Stream")
    video_tag.setGenres(["Live Communication"])
    video_tag.setPlot("Connects directly to the raw 1080p hardware-accelerated video pipeline.")
    video_tag.setMediaType("video")
    
    video_item.setProperty('IsPlayable', 'true') 
    video_url = f"{base_url}?action=play_video"
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

def run_ffmpeg_multiplexer():
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


    # =========================================================================
    # ENGINE 1: YOUR PERFECT WORKING VIDEO PIPELINE (100% UNTOUCHED)
    # =========================================================================
    video_cmd = [
        ffmpeg_bin, "-y", "-re",
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
    ]

    # =========================================================================
    # ENGINE 2: PARALLEL PURE-AUDIO PIPELINE (ISOLATED)
    # =========================================================================
    audio_cmd = [
        ffmpeg_bin, "-y", "-re",
        # Force a steady wallclock timeline on your native upmixed C packets
        "-use_wallclock_as_timestamps", "1",
        "-f", "s16le", "-ch_layout", "stereo", "-ar", "48000", "-ac", "2",
        "-i", "udp://127.0.0.1:28889?listen=1&overrun_nonfatal=1&buffer_size=524288&reuse=1&timeout=500000",
        "-map", "0:a",
        "-c:a", "aac", "-b:a", "128k",
        "-af", "aresample=async=1:min_hard_comp=0.100000:first_pts=0",
        "-f", "mpegts",
        "-mpegts_flags", "resend_headers+initial_discontinuity",
        "-fflags", "nobuffer+flush_packets", "-flush_packets", "1",
        "udp://127.0.0.1:28891?pkt_size=1316&overrun_nonfatal=1" # Outputting on independent port 28891
    ]
    
    try:
        xbmc.log("[plugin.video.koditox] Spawning isolated dual-engine pipelines...", xbmc.LOGINFO)
        
        # Launch Video Node
        ffmpeg_process = subprocess.Popen(
            video_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE, close_fds=True, creationflags=creation_flags
        )
        
        # Launch Audio Node
        ## AUDIO ## ffmpeg_audio_process = subprocess.Popen(
        ## AUDIO ##     audio_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE, close_fds=True, creationflags=creation_flags
        ## AUDIO ## )
        
        xbmc.sleep(800)
        
        ## AUDIO ## if ffmpeg_process.poll() is not None or ffmpeg_audio_process.poll() is not None:
        if ffmpeg_process.poll() is not None:
            return False

        # --- NEW IMPLEMENTATION: Save PIDs to allow cross-thread absolute termination ---
        ## AUDIO ## save_engine_pids(ffmpeg_process.pid, ffmpeg_audio_process.pid)
        save_engine_pids(ffmpeg_process.pid, None)
        # ---------------------------------------------------------------------------------


        return True
        
    except Exception as e:
        xbmc.log(f"[plugin.video.koditox] Process spawn exception: {str(e)}", xbmc.LOGERROR)
        return False


tox_monitor = None


def play_video(handle, native_lib):
    global ffmpeg_process, ffmpeg_audio_process, tox_monitor
    list_item = xbmcgui.ListItem("Tox Video Call")
    
    try:
        # --- NEW IMPLEMENTATION: Pure process termination by PID baseline ---
        hard_kill_tracked_pids()
        ffmpeg_process = None
        ffmpeg_audio_process = None
        # ---------------------------------------------------------------------

        if ffmpeg_process is None:
            if not run_ffmpeg_multiplexer():
                raise RuntimeError("FFmpeg engines failed to initialize loop ports.")
            xbmc.sleep(800) 

        ## AUDIO ## ff_opts = "-f mpegts -probesize 16384 -analyzeduration 100000 -fflags nobuffer+genpts+igndts -flags low_delay"
        ff_opts = "-f mpegts -probesize 16384 -analyzeduration 100000 -fflags nobuffer+genpts+igndts -flags low_delay -an"
        
        stream_url = (
            f"udp://127.0.0.1:28890?overrun_nonfatal=1&fifo_size=50000"
            f"|ffmpegoptions={ff_opts}"
            ## AUDIO ## f"|inputstream.ffmpegdirect.audio_src=udp://127.0.0.1:28891?overrun_nonfatal=1&fifo_size=50000"
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
        list_item.setProperty('inputstream.ffmpegdirect.has_audio', 'false')

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
                
            ## AUDIO ## if ffmpeg_audio_process is not None and ffmpeg_audio_process.poll() is not None:
            ## AUDIO ##     xbmc.log("[plugin.video.koditox] Audio engine disconnected (Remote hangup). Breaking loop.", xbmc.LOGINFO)
            ## AUDIO ##     break
                
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
        ## AUDIO ## with open(pid_file, "w") as f:
        ## AUDIO ##     f.write(f"{video_pid},{audio_pid}")
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
        toxav_network_roundtrip_ms = ctypes.c_int64(0)
        toxav_play_buffer_entries = ctypes.c_int32(0)
        toxav_incoming_fps = ctypes.c_int64(0)
        string_buffer = ctypes.create_string_buffer(200)

        while self.is_running and not self.kodi_monitor.abortRequested():
            # Call into the C function passing references to our variables
            new_data_available = self.native_lib.get_latest_telemetry(
                ctypes.byref(friend_number),
                ctypes.byref(toxav_decoder_bitrate),
                ctypes.byref(toxav_network_roundtrip_ms),
                ctypes.byref(toxav_play_buffer_entries),
                ctypes.byref(toxav_incoming_fps),
                ctypes.cast(string_buffer, ctypes.c_void_p)
            )
            
            # If the C layer returned 1, update the visible text layout
            ## xbmc.log(f"[plugin.video.koditox] Polled new metrics", xbmc.LOGINFO)
            native_string = string_buffer.value.decode('utf-8', errors='ignore')
            if self.osd is not None:
                    status_text = f"FPS: {toxav_incoming_fps.value} BR: {toxav_decoder_bitrate.value}"
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
        play_video(handle, native_lib)
    else:
        build_main_menu(handle, base_url, native_lib, profile_path)

if __name__ == '__main__':
    run()
