#define _GNU_SOURCE

#include <tox/tox.h>
#ifdef TOX_HAVE_TOXUTIL
    #include <tox/toxutil.h>
#endif
#include <tox/toxav.h>

#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>

// Cross-platform threading and sleeping
#if defined(_WIN32) || defined(_WIN64)
    #define EXPORT __declspec(dllexport)
    #include <windows.h>
    #define THREAD_RETURN DWORD WINAPI
    typedef HANDLE thread_t;
#else
    #define EXPORT __attribute__((visibility("default")))
    #include <pthread.h>
    #include <unistd.h>
    #define THREAD_RETURN void*
    typedef pthread_t thread_t;
#endif

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #define SOCKET_TYPE SOCKET
    #define CLOSE_SOCKET(s) closesocket(s)
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #define SOCKET_TYPE int
    #define INVALID_SOCKET -1
    #define CLOSE_SOCKET(s) close(s)
#endif


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_PATH_LEN 2048
#define PIPE_WRITE(ptr, size, count, stream) fwrite(ptr, size, count, stream)
#define DEFAULT_GLOBAL_VID_BITRATE_NORMAL_QUALITY 600
#define DEFAULT_GLOBAL_AUD_BITRATE 32

static SOCKET_TYPE udp_socket = INVALID_SOCKET;
static struct sockaddr_in kodi_addr;
static uint8_t ts_packet_counter = 0;
static uint32_t frame_count = 0;
static uint32_t c_pts_counter = 0;
static SOCKET_TYPE udp_audio_socket = INVALID_SOCKET;
static struct sockaddr_in kodi_audio_addr;


static char g_profile_dir[MAX_PATH_LEN] = {0};
static Tox *global_tox = NULL;
static ToxAV *global_toxav = NULL;
static char g_tox_id_hexstr[TOX_ADDRESS_SIZE * 2 + 1] = {0};
static const char *tox_name = "KodiTox";

static FILE *video_pipe = NULL;
volatile int is_streaming_active = 0;

// Thread tracking variables
static volatile bool g_loop_running = false;
static volatile bool gav_loop_running = false;
static volatile bool gava_loop_running = false;
static thread_t g_worker_thread;
static thread_t gav_worker_thread;
static thread_t gava_worker_thread;

// Struct to represent a standard bootstrap node and TCP relay
typedef struct NetworkNode {
    const char *address;
    uint16_t port;
    const char *key_hex;
} NetworkNode;

// Stable nodes from the official Tox network functioning as both UDP Bootstrap and TCP Relays
static const NetworkNode bootstrap_nodes[] = {
    {"3.0.24.15",                         33445, "E20ABCF38CDBFFD7D04B29C956B33F7B27A3BB7AF0618101617B036E4AEA402D"},
    {"43.198.227.166",                    33445, "AD13AB0D434BCE6C83FE2649237183964AE3341D0AFB3BE1694B18505E4E135E"},
    {"43.198.227.166",                    3389,  "AD13AB0D434BCE6C83FE2649237183964AE3341D0AFB3BE1694B18505E4E135E"},
    {"91.146.66.26",                      33445, "B5E7DAC610DBDE55F359C7F8690B294C8E4FCEC4385DE9525DBFA5523EAD9D53"},
    {"144.217.167.73",                    33445, "7E5668E0EE09E19F320AD47902419331FFEE147BB3606769CFBE921A2A2FD34C"},
    {"172.104.215.182",                     443, "DA2BD927E01CD05EBCC2574EBE5BEBB10FF59AE0B2105A7D1E2B40E49BB20239"},
    {"188.214.122.30",                    33445, "2A9F7A620581D5D1B09B004624559211C5ED3D1D712E8066ACDB0896A7335705"},
    {"205.185.115.131",                      53, "3091C6BEB2A993F1C6300C16549FABA67098FF3D62C6D253828B531470B53D68"},
    {"205.185.115.131",                   33445, "3091C6BEB2A993F1C6300C16549FABA67098FF3D62C6D253828B531470B53D68"},
    {"tox1.mf-net.eu",                    33445, "B3E5FA80DC8EBD1149AD2AB35ED8B85BD546DEDE261CA593234C619249419506"},
    {"tox.initramfs.io",                  33445, "3F0A45A268367C1BEA652F258C85F4A66DA76BCAA667A49E770BCC4917AB6A25"},
    {"tox.hidemybits.com",                33445, "5D57B95EE4A7F37BA031DAD0CBD9510A9C96FFE09C1CE24A9C33746F39817D6E"},
    {"tox.hidemybits.com",                443,   "5D57B95EE4A7F37BA031DAD0CBD9510A9C96FFE09C1CE24A9C33746F39817D6E"},
    {"2400:8902::f03c:93ff:fe69:bf77",    33445, "F76A11284547163889DDC89A7738CF271797BF5E5E220643E97AD3C7E7903D55"},
    {"2600:3c04::f03c:92ff:fe30:5df",     33445, "D46E97CF995DC1820B92B7D899E152A217D36ABE22730FEA4B6BF1BFC06C617C"},
};


// Forward declarations
Tox *create_tox(const char* p_dir);
void update_savedata_file(const Tox *tox);
EXPORT const char* init(const char* profile_dir);





static void write_log(const char *format, ...) {
    // Cross-platform safe path for file generation
    const char *log_path = "/tmp/koditox.log";
#if defined(_WIN32) || defined(_WIN64)
    log_path = "C:\\Windows\\Temp\\koditox.log";
#endif

    FILE *f = fopen(log_path, "a");
    if (f) {
        // 1. Generate and write the timestamp anchor prefix
        time_t now = time(NULL);
        struct tm *t = localtime(&now);
        char time_str[32];
        strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", t);
        fprintf(f, "[%s] ", time_str);

        // 2. Initialize variable arguments and print payload
        va_list args;
        va_start(args, format);
        vfprintf(f, format, args);
        va_end(args);

        // 3. Append trailing newline and flush buffers cleanly
        fprintf(f, "\n");
        fflush(f);
        fclose(f);
    }
}


EXPORT const char* get_stream_url() {
    return "/tmp/koditox_video.fifo";
}

// Internal utility function to convert a Hex String into a Raw Byte Array
static void hex_to_bin(const char *hex, uint8_t *bin) {
    for (size_t i = 0; i < TOX_PUBLIC_KEY_SIZE; i++) {
        unsigned int byte;
        sscanf(&hex[i * 2], "%2x", &byte);
        bin[i] = (uint8_t)byte;
    }
}

// Cross-platform sleep helper
static void sleep_ms(int milliseconds) {
#if defined(_WIN32) || defined(_WIN64)
    Sleep(milliseconds);
#else
    usleep(milliseconds * 1000);
#endif
}


// Background thread loop function
static THREAD_RETURN tox_worker_loop(void *arg) {
#if defined(__linux__) || defined(__ANDROID__)
    pthread_setname_np(pthread_self(), "tox_it");
#elif defined(__APPLE__)
    pthread_setname_np("tox_it");
#endif

    write_log("tox thread starting ...");
    while (g_loop_running) {
        if (global_tox != NULL) {
            tox_iterate(global_tox, NULL);
        }
        sleep_ms(4);
    }
    write_log("tox thread finished");
    return 0;
}


// Background thread loop function
static THREAD_RETURN toxav_worker_loop(void *arg) {
#if defined(__linux__) || defined(__ANDROID__)
    pthread_setname_np(pthread_self(), "toxav_it");
#elif defined(__APPLE__)
    pthread_setname_np("toxav_it");
#endif

    write_log("toxav thread starting ...");
    while (gav_loop_running) {
        if (global_toxav != NULL) {
            toxav_iterate(global_toxav);
        }
        sleep_ms(4);
    }
    write_log("toxav thread finished");
    return 0;
}

// Background thread loop function
static THREAD_RETURN toxava_worker_loop(void *arg) {
#if defined(__linux__) || defined(__ANDROID__)
    pthread_setname_np(pthread_self(), "toxava_it");
#elif defined(__APPLE__)
    pthread_setname_np("toxava_it");
#endif

    write_log("toxava thread starting ...");
    while (gava_loop_running) {
        if (global_toxav != NULL) {
            toxav_iterate(global_toxav);
        }
        sleep_ms(10);
    }
    write_log("toxava thread finished");
    return 0;
}



Tox *create_tox(const char* p_dir)
{
    Tox *tox;
    struct Tox_Options options;
    tox_options_default(&options);
    
    options.udp_enabled = true;
    options.ipv6_enabled = true;
    options.local_discovery_enabled = true;
    options.hole_punching_enabled = true;
    options.tcp_port = 0; 
    options.proxy_type = TOX_PROXY_TYPE_NONE;

    char savedata_filename[MAX_PATH_LEN];
    snprintf(savedata_filename, sizeof(savedata_filename), "%ssavedata.tox", g_profile_dir);

    FILE *f = fopen(savedata_filename, "rb");
    if (f)
    {
        fseek(f, 0, SEEK_END);
        long fsize = ftell(f);
        fseek(f, 0, SEEK_SET);
        uint8_t *savedata = calloc(1, fsize);
        size_t dummy = fread(savedata, fsize, 1, f);
        fclose(f);
        options.savedata_type = TOX_SAVEDATA_TYPE_TOX_SAVE;
        options.savedata_data = savedata;
        options.savedata_length = fsize;
#ifdef TOX_HAVE_TOXUTIL
        tox = tox_utils_new(&options, NULL);
#else
        tox = tox_new(&options, NULL);
#endif
        free((void *)savedata);
    }
    else
    {
#ifdef TOX_HAVE_TOXUTIL
        tox = tox_utils_new(&options, NULL);
#else
        tox = tox_new(&options, NULL);
#endif
    }
    return tox;
}

void update_savedata_file(const Tox *tox)
{
    if (!tox) return;
    size_t size = tox_get_savedata_size(tox);
    char *savedata = calloc(1, size);
    tox_get_savedata(tox, (uint8_t *)savedata);

    char savedata_filename[MAX_PATH_LEN];
    snprintf(savedata_filename, sizeof(savedata_filename), "%ssavedata.tox", g_profile_dir);
    char savedata_tmp_filename[MAX_PATH_LEN];
    snprintf(savedata_tmp_filename, sizeof(savedata_tmp_filename), "%ssavedata.tox.tmp", g_profile_dir);

    FILE *f = fopen(savedata_tmp_filename, "wb");
    if (f) {
        fwrite(savedata, size, 1, f);
        fclose(f);
        rename(savedata_tmp_filename, savedata_filename);
    }
    free(savedata);
}

EXPORT const char* init(const char* profile_dir) {
    if (profile_dir != NULL && strlen(g_profile_dir) == 0) {
        snprintf(g_profile_dir, sizeof(g_profile_dir), "%s", profile_dir);
    }

    if (global_tox != NULL) {
        return g_tox_id_hexstr;
    }

    global_tox = create_tox(g_profile_dir);
    if (!global_tox) {
        return "error_initializing_tox_instance";
    }

    tox_self_set_name(global_tox, (uint8_t *)tox_name, strlen(tox_name), NULL);
    update_savedata_file(global_tox);

    uint8_t tox_id_bin[TOX_ADDRESS_SIZE];
    tox_self_get_address(global_tox, tox_id_bin);
    for (size_t i = 0; i < TOX_ADDRESS_SIZE; i++) {
        snprintf(&g_tox_id_hexstr[i * 2], 3, "%02X", tox_id_bin[i]);
    }

    TOXAV_ERR_NEW rc;
    global_toxav = toxav_new(global_tox, &rc);
    toxav_audio_iterate_seperation(global_toxav, true);

    return g_tox_id_hexstr;
}

void friend_request_cb(Tox *tox, const uint8_t *public_key, const uint8_t *message, size_t length, void *user_data)
{
    write_log("new friend request");
    uint32_t friendnum = tox_friend_add_norequest(tox, public_key, NULL);
    update_savedata_file(global_tox);
}

void on_tox_friend_status(Tox *tox, uint32_t friend_number, TOX_USER_STATUS status, void *user_data)
{
}

void friend_name_cb(Tox *tox, uint32_t friend_number, const uint8_t *name, size_t length, void *user_data)
{
}

void self_connection_status_cb(Tox *tox, TOX_CONNECTION connection_status, void *user_data)
{
    write_log("self connection status change: %d", (int)connection_status);
}

void friendlist_onConnectionChange(Tox *m, uint32_t num, TOX_CONNECTION connection_status, void *user_data)
{
    write_log("friend connection status change: %d", (int)connection_status);
}

static void t_toxav_call_cb(ToxAV *av, uint32_t friend_number, bool audio_enabled, bool video_enabled, void *user_data)
{
    write_log("t_toxav_call_cb: incoming call ...");
    TOXAV_ERR_ANSWER err;
    toxav_answer(av, friend_number, DEFAULT_GLOBAL_AUD_BITRATE, DEFAULT_GLOBAL_VID_BITRATE_NORMAL_QUALITY, &err);
}

static void t_toxav_call_state_cb(ToxAV *av, uint32_t friend_number, uint32_t state, void *user_data)
{
    write_log("t_toxav_call_state_cb: call state change fn: %d state: %d", (int)friend_number, (int)state);
}

static void t_toxav_bit_rate_status_cb(ToxAV *av, uint32_t friend_number,
                                       uint32_t audio_bit_rate, uint32_t video_bit_rate,
                                       void *user_data)
{
}

static void t_toxav_receive_video_frame_cb(ToxAV *av, uint32_t friend_number,
        uint16_t width, uint16_t height,
        uint8_t const *y, uint8_t const *u, uint8_t const *v,
        int32_t ystride, int32_t ustride, int32_t vstride,
        void *user_data)
{
}




// Maps Program 1 to PMT PID 0x1000. Remaining bytes automatically padded.
static const uint8_t pat_packet[188] = {
    0x47, 0x40, 0x00, 0x10, 0x00, 0x00, 0xB0, 0x0D, 
    0x00, 0x01, 0xC1, 0x00, 0x00, 0x00, 0x01, 0xE1, 
    0x00, 0xE8, 0xF9, 0x5E, 0x7D
};

// Specifies Stream Type 0x1B (H.264 Video) on PID 0x1001. Remaining bytes automatically padded.
static const uint8_t pmt_packet[188] = {
    0x47, 0x50, 0x00, 0x10, 0x00, 0x02, 0xB0, 0x12, 
    0x00, 0x01, 0xC1, 0x00, 0x00, 0xE1, 0x00, 0xF0, 
    0x00, 0x1B, 0xE1, 0x01, 0xF0, 0x00, 0x2A, 0xB0, 
    0x93, 0xA3
};














// Track current stream canvas state
static int current_width = 0;
static int current_height = 0;

// Helper to read individual bits from the raw SPS byte array
typedef struct {
    const uint8_t *data;
    size_t size;
    size_t byte_idx;
    size_t bit_idx;
} BitParser;

static uint32_t read_bit(BitParser *p) {
    if (p->byte_idx >= p->size) return 0;
    uint32_t bit = (p->data[p->byte_idx] >> (7 - p->bit_idx)) & 0x01;
    p->bit_idx++;
    if (p->bit_idx == 8) {
        p->bit_idx = 0;
        p->byte_idx++;
        // Skip H.264 emulation prevention bytes (0x000003) automatically
        if (p->byte_idx + 2 < p->size && 
            p->data[p->byte_idx] == 0x00 && 
            p->data[p->byte_idx+1] == 0x00 && 
            p->data[p->byte_idx+2] == 0x03) {
            p->byte_idx += 1; // Skip the emulation byte jump
        }
    }
    return bit;
}

// Read Exponential-Golomb unsigned integer values (ue(v))
static uint32_t read_ue(BitParser *p) {
    uint32_t zero_bits = 0;
    while (read_bit(p) == 0 && zero_bits < 32) {
        zero_bits++;
    }
    uint32_t val = 0;
    for (uint32_t i = 0; i < zero_bits; i++) {
        val = (val << 1) | read_bit(p);
    }
    return ((1 << zero_bits) - 1) + val;
}

// Parses raw SPS payload bits to calculate dimensions
static void parse_and_check_sps(const uint8_t *sps, size_t size) {
    if (size < 4) return;
    
    BitParser p = { sps, size, 0, 0 };
    
    // Skip NAL header byte (usually 0x67)
    p.byte_idx = 1;
    
    uint8_t profile_idc = sps[p.byte_idx++];
    p.byte_idx++; // Skip constraint flags
    uint8_t level_idc = sps[p.byte_idx++];
    read_ue(&p);  // Skip sps_id
    
    if (profile_idc == 100 || profile_idc == 110 || profile_idc == 122 || 
        profile_idc == 244 || profile_idc == 44 || profile_idc == 83 || 
        profile_idc == 86 || profile_idc == 118 || profile_idc == 128) {
        uint32_t chroma_format_idc = read_ue(&p);
        if (chroma_format_idc == 3) {
            read_bit(&p); // separate_colour_plane_flag
        }
        read_ue(&p); // bit_depth_luma_minus8
        read_ue(&p); // bit_depth_chroma_minus8
        read_bit(&p); // qpprime_y_zero_transform_bypass_flag
        uint32_t seq_scaling_matrix_present_flag = read_bit(&p);
        if (seq_scaling_matrix_present_flag) {
            uint32_t loops = (chroma_format_idc != 3) ? 8 : 12;
            for (uint32_t i = 0; i < loops; i++) {
                if (read_bit(&p)) { // seq_scaling_list_present_flag
                    // Skip scaling list details
                    int last = 8, next = 8;
                    for (int j = 0; j < (i < 6 ? 16 : 64); j++) {
                        if (next != 0) {
                            int delta = read_ue(&p); // signed mapping approximation
                            next = (last + delta) % 256;
                        }
                        last = (next == 0) ? last : next;
                    }
                }
            }
        }
    }
    
    read_ue(&p); // log2_max_frame_num_minus4
    uint32_t pic_order_cnt_type = read_ue(&p);
    if (pic_order_cnt_type == 0) {
        read_ue(&p); // log2_max_pic_order_cnt_lsb_minus4
    } else if (pic_order_cnt_type == 1) {
        read_bit(&p); // delta_pic_order_always_zero_flag
        read_ue(&p);  // offset_for_non_ref_pic
        read_ue(&p);  // offset_for_top_to_bottom_field
        uint32_t num_ref_frames_in_pic_order_cnt_cycle = read_ue(&p);
        for (uint32_t i = 0; i < num_ref_frames_in_pic_order_cnt_cycle; i++) {
            read_ue(&p); // offset_for_ref_frame
        }
    }
    
    read_ue(&p); // max_num_ref_frames
    read_bit(&p); // gaps_in_frame_num_value_allowed_flag
    
    // Core Dimension Calculations
    uint32_t pic_width_in_mbs_minus1 = read_ue(&p);
    uint32_t pic_height_in_map_units_minus1 = read_ue(&p);
    uint32_t frame_mbs_only_flag = read_bit(&p);
    
    if (!frame_mbs_only_flag) {
        read_bit(&p); // field_pic_flag
    }
    read_bit(&p); // alloc_frame_cropping_flag
    
    // Convert Macroblocks to absolute Pixels
    int width = (pic_width_in_mbs_minus1 + 1) * 16;
    int height = (pic_height_in_map_units_minus1 + 1) * 16 * (2 - frame_mbs_only_flag);
    
    // Check if the resolution changed during runtime execution
    if (width != current_width || height != current_height) {
        write_log("[Koditox Resolution] CHANGE DETECTED: %dx%dp -> %dx%dp\n", current_width, current_height, width, height);
        current_width = width;
        current_height = height;
    }
}
























void native_start_video_stream(const char* dummy_path) {
    // === YOUR ORIGINAL VIDEO INITIALIZATION (UNTOUCHED) ===
    if (udp_socket != INVALID_SOCKET) return;


    // FIX 1: Ignore SIGPIPE globally on Linux so broken pipes return an error code instead of crashing Kodi
#ifndef _WIN32
    // struct sigaction sa;
    // sa.sa_handler = SIG_IGN;
    // sigemptyset(&sa.sa_mask);
    // sa.sa_flags = 0;
    // sigaction(SIGPIPE, &sa, NULL);
#else
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif

    udp_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (udp_socket == INVALID_SOCKET) return;

    int low_latency_socket_buf = 2 * 1024 * 1024; // 64 * 1024;
    setsockopt(udp_socket, SOL_SOCKET, SO_RCVBUF, (const char*)&low_latency_socket_buf, sizeof(low_latency_socket_buf));
    setsockopt(udp_socket, SOL_SOCKET, SO_SNDBUF, (const char*)&low_latency_socket_buf, sizeof(low_latency_socket_buf));

    memset(&kodi_addr, 0, sizeof(kodi_addr));
    kodi_addr.sin_family = AF_INET;
    kodi_addr.sin_port = htons(28888);
    kodi_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    ts_packet_counter = 0;
    frame_count = 0;

    // === NEW: INITIALIZE AUDIO SOCKET ON PORT 28889 ===
    udp_audio_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (udp_audio_socket != INVALID_SOCKET) {
        setsockopt(udp_audio_socket, SOL_SOCKET, SO_SNDBUF, (const char*)&low_latency_socket_buf, sizeof(low_latency_socket_buf));
        
        memset(&kodi_audio_addr, 0, sizeof(kodi_audio_addr));
        kodi_audio_addr.sin_family = AF_INET;
        kodi_audio_addr.sin_port = htons(28889); // Audio port
        kodi_audio_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    }

    // Toggle execution flag ON
    is_streaming_active = 1; 
}


void native_stop_video_stream(const char* dummy_path) {

    // FIX 3: Turn off visibility instantly to freeze asynchronous callback operations
    is_streaming_active = 0;

    // Give any active, running sendto loops a microscopic window to exit their blocks safely
    #ifndef _WIN32
    usleep(10000); // 10ms delay sleep
    #else
    Sleep(10);
    #endif

    // Your original video cleanup
    if (udp_socket != INVALID_SOCKET) {
        CLOSE_SOCKET(udp_socket);
        udp_socket = INVALID_SOCKET;
    }
    // Clean up audio socket
    if (udp_audio_socket != INVALID_SOCKET) {
        CLOSE_SOCKET(udp_audio_socket);
        udp_audio_socket = INVALID_SOCKET;
    }
#ifdef _WIN32
    WSACleanup();
#endif
}


static void send_video_ts_packet(const uint8_t *payload_chunk, size_t size, int is_start_of_frame) {
    uint8_t packet[188]; // Make sure [188] is explicitly declared here
    
    packet[0] = 0x47; // Sync Byte
    
    // Set PID 0x1001 (Video Stream)
    packet[1] = (is_start_of_frame ? 0x40 : 0x00) | 0x10; 
    packet[2] = 0x01; 
    
    // Continuity Counter
    packet[3] = 0x10 | (ts_packet_counter & 0x0F); 
    ts_packet_counter++;

    // Copy payload data up to 184 bytes
    memcpy(&packet[4], payload_chunk, size);
    
    // Fill the remainder of the packet with 0xFF padding if data block is short
    if (size < 184) {
        memset(&packet[4 + size], 0xFF, 184 - size);
    }

    sendto(udp_socket, (const char*)packet, 188, MSG_NOSIGNAL, (struct sockaddr*)&kodi_addr, sizeof(kodi_addr));
}







static void inject_annexb_timing_header(uint32_t pts_val) {
    // Generate an in-band FFmpeg low-overhead alignment timing marker
    // This tells Kodi's player core exactly when to display the upcoming frame
    uint8_t timing_marker[12];
    timing_marker[0] = 0x00; 
    timing_marker[1] = 0x00; 
    timing_marker[2] = 0x00; 
    timing_marker[3] = 0x01; // Annex-B Prefix
    timing_marker[4] = 0x09; // Access Unit Delimiter (AUD) NAL type
    timing_marker[5] = 0xF0; // Primary pic type (I/P/B baseline safe)
    
    // Simple Big-Endian payload size representation trick for FFmpeg parsing hooks
    timing_marker[6] = (pts_val >> 24) & 0xFF;
    timing_marker[7] = (pts_val >> 16) & 0xFF;
    timing_marker[8] = (pts_val >> 8) & 0xFF;
    timing_marker[9] = pts_val & 0xFF;
    timing_marker[10] = 0x00;
    timing_marker[11] = 0x00;

    sendto(udp_socket, (const char*)timing_marker, sizeof(timing_marker), MSG_NOSIGNAL, 
           (struct sockaddr*)&kodi_addr, sizeof(kodi_addr));
}



static void transmit_raw_socket_chunk(const uint8_t *data, size_t size) {
    size_t written = 0;
    while (written < size) {
        size_t chunk = (size - written > 1300) ? 1300 : (size - written);
        sendto(udp_socket, (const char*)&data[written], chunk, MSG_NOSIGNAL, 
               (struct sockaddr*)&kodi_addr, sizeof(kodi_addr));
        written += chunk;
    }
}

static void t_toxav_receive_video_frame_h264_cb(ToxAV *av, uint32_t friend_number,
        const uint8_t *buf, const uint32_t buf_size, void *user_data) 
{
    //**// write_log("t_toxav_receive_video_frame_h264_cb:001");
    if (!is_streaming_active)
    {
        return;
    }

    if (udp_socket == INVALID_SOCKET || buf == NULL || buf_size == 0) {
        return;
    }

#if 0
    // Scan incoming frame chunks for inline NAL unit indicators
    for (size_t i = 0; i < buf_size - 4; i++) {
        if (buf[i] == 0x00 && buf[i+1] == 0x00) {
            size_t start_code_len = 0;
            if (buf[i+2] == 0x01) start_code_len = 3;
            else if (buf[i+2] == 0x00 && buf[i+3] == 0x01) start_code_len = 4;
            
            if (start_code_len > 0) {
                uint8_t nal_type = buf[i + start_code_len] & 0x1F;
                if (nal_type == 7) { // 7 = Sequence Parameter Set (SPS)
                    // Safely isolate the SPS block data
                    parse_and_check_sps(&buf[i + start_code_len], buf_size - (i + start_code_len));
                    break;
                }
            }
        }
    }

    // ==========================================
    // INITIAL HANDSHAKE INJECTION (BURST ONLY)
    // ==========================================
    // Only inject if we haven't read a valid resolution parameter natively yet
    if (frame_count < 60 && current_width == 0) {
        if (frame_count % 10 == 0) {
            static const uint8_t forced_sps[] = {
                0x00, 0x00, 0x00, 0x01, 0x67, 0x42, 0xC0, 0x28,       
                0xDA, 0x01, 0xE0, 0x08, 0x9F, 0x96, 0x10, 0x00, 
                0x00, 0x03, 0x00, 0x10, 0x00, 0x00, 0x03, 0x01, 
                0x40, 0x46, 0x20, 0x01, 0x1C
            };
            static const uint8_t forced_pps[] = {
                0x00, 0x00, 0x00, 0x01, 0x68, 0xCE, 0x3C, 0x80        
            };
            transmit_raw_socket_chunk(forced_sps, sizeof(forced_sps));
            transmit_raw_socket_chunk(forced_pps, sizeof(forced_pps));
        }
    }
    frame_count++;

    // Separator delimiter
    static const uint8_t aud_marker[] = { 0x00, 0x00, 0x00, 0x01, 0x09, 0xF0 };
    sendto(udp_socket, (const char*)aud_marker, sizeof(aud_marker), MSG_NOSIGNAL, 
           (struct sockaddr*)&kodi_addr, sizeof(kodi_addr));

#endif

    // Send payload straight to loopback
    transmit_raw_socket_chunk(buf, buf_size);
}






static void t_toxav_receive_video_frame_pts_cb(ToxAV *av, uint32_t friend_number,
        uint16_t width, uint16_t height,
        const uint8_t *y, const uint8_t *u, const uint8_t *v,
        int32_t ystride, int32_t ustride, int32_t vstride,
        void *user_data, uint64_t pts)
{
}




static void t_toxav_receive_audio_frame_cb(ToxAV *av, uint32_t friend_number,
        int16_t const *pcm,
        size_t sample_count,
        uint8_t channels,
        uint32_t sampling_rate,
        void *user_data)
{
}





// === FIXED: AUDIO STREAMING CALLBACK WITH NATIVE MONO->STEREO UPMIXING ===
static void t_toxav_receive_audio_frame_pts_cb(ToxAV *av, uint32_t friend_number,
        int16_t const *pcm,
        size_t sample_count,
        uint8_t channels,
        uint32_t sampling_rate,
        void *user_data,
        uint64_t pts)
{


    // ************** ATTENTION **************
    // ************** ATTENTION **************
    // ************** ATTENTION **************
    // ************** ATTENTION **************
    //   disabled for now. the kodi video addon can not play audio and video together at this time
    //   and if you do not send audio on your call nothing will play at all.
    //   need to find out another time why
    return;
    // ************** ATTENTION **************
    // ************** ATTENTION **************
    // ************** ATTENTION **************
    // ************** ATTENTION **************



    if (!is_streaming_active)
    {
        return;
    }

    if (udp_audio_socket == INVALID_SOCKET || pcm == NULL || sample_count == 0) {
        return;
    }

    // Protect pipeline: Ignore non-48000Hz frames to prevent FFmpeg timeline collapse
    if (sampling_rate != 48000) {
        return; 
    }

    // Pointers for final data tracking
    const uint8_t *send_data = (const uint8_t *)pcm;
    size_t final_pcm_size = 0;

    // Use a stack buffer for real-time mono-to-stereo conversion
    // ToxAV audio frames are typically small (e.g., 960 or 1920 samples)
    #define MONO_BUFFER_MAX_SAMPLES 4096
    int16_t stereo_lookup_buffer[MONO_BUFFER_MAX_SAMPLES * 2];

    if (channels == 1) {
        // Safety bounds check
        if (sample_count > MONO_BUFFER_MAX_SAMPLES) {
            sample_count = MONO_BUFFER_MAX_SAMPLES;
        }

        // Duplicate the mono channel sample into left and right slots
        for (size_t i = 0; i < sample_count; i++) {
            stereo_lookup_buffer[i * 2]     = pcm[i]; // Left Channel
            stereo_lookup_buffer[i * 2 + 1] = pcm[i]; // Right Channel
        }

        // Redirect stream targets to the upmixed stereo buffer
        send_data = (const uint8_t *)stereo_lookup_buffer;
        final_pcm_size = sample_count * 2 * sizeof(int16_t);
    } 
    else if (channels == 2) {
        // Already stereo, pass directly through
        final_pcm_size = sample_count * channels * sizeof(int16_t);
    } 
    else {
        // Drop rare multi-channel layouts (e.g. 5.1 surrounding sound configurations)
        return;
    }

    // Chunk and stream the verified stereo PCM data directly to port 28889
    size_t written = 0;
    while (written < final_pcm_size) {
        size_t chunk = (final_pcm_size - written > 1300) ? 1300 : (final_pcm_size - written);
        sendto(udp_audio_socket, (const char*)&send_data[written], chunk, MSG_NOSIGNAL, 
               (struct sockaddr*)&kodi_audio_addr, sizeof(kodi_audio_addr));
        written += chunk;
    }
}





// A structure to safely house the latest network updates
typedef struct {
    uint32_t friend_number;
    int64_t toxav_decoder_bitrate;
    int64_t toxav_network_roundtrip_ms;
    int32_t toxav_play_buffer_entries;
    int64_t toxav_incoming_fps;
    char status_message[100];
    int data_ready; // Acts as a flag: 1 means new data arrived, 0 means no change
} ToxTelemetryData;

// Global thread-local memory allocation
static ToxTelemetryData g_latest_telemetry = {0, 0, 0, 0, 0, "", 0};

// Your actual Tox library callback function running on the network thread
static void t_toxav_call_comm_cb(ToxAV *av, uint32_t friend_number, TOXAV_CALL_COMM_INFO comm_value,
                                 int64_t comm_number, void *user_data)
{
    // write_log("t_toxav_call_comm_cb ... %d", (int)comm_value);

#if 0
    if (comm_value == TOXAV_CALL_COMM_DECODER_IN_USE_VP8)
    {
        write_log("TOXAV_CALL_COMM_DECODER_IN_USE_VP8:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_DECODER_IN_USE_H264)
    {
        write_log("TOXAV_CALL_COMM_DECODER_IN_USE_H264:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_DECODER_IN_USE_H265)
    {
        write_log("TOXAV_CALL_COMM_DECODER_IN_USE_H265:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_ENCODER_IN_USE_VP8)
    {
        write_log("TOXAV_CALL_COMM_ENCODER_IN_USE_VP8:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_ENCODER_IN_USE_H264)
    {
        write_log("TOXAV_CALL_COMM_ENCODER_IN_USE_H264:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_ENCODER_IN_USE_H265)
    {
        write_log("TOXAV_CALL_COMM_ENCODER_IN_USE_H265:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_ENCODER_IN_USE_H264_OMX_PI)
    {
        write_log("TOXAV_CALL_COMM_ENCODER_IN_USE_H264_OMX_PI:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_DECODER_CURRENT_BITRATE)
    {
        write_log("TOXAV_CALL_COMM_DECODER_CURRENT_BITRATE:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_NETWORK_ROUND_TRIP_MS)
    {
        write_log("TOXAV_CALL_COMM_NETWORK_ROUND_TRIP_MS:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_PLAY_DELAY)
    {
        write_log("TOXAV_CALL_COMM_PLAY_DELAY:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_PLAY_BUFFER_ENTRIES)
    {
        write_log("TOXAV_CALL_COMM_PLAY_BUFFER_ENTRIES:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_DECODER_H264_PROFILE)
    {
        write_log("TOXAV_CALL_COMM_DECODER_H264_PROFILE:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_DECODER_H264_LEVEL)
    {
        write_log("TOXAV_CALL_COMM_DECODER_H264_LEVEL:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_PLAY_VIDEO_ORIENTATION)
    {
        write_log("TOXAV_CALL_COMM_PLAY_VIDEO_ORIENTATION:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_ENCODER_CURRENT_BITRATE)
    {
        write_log("TOXAV_CALL_COMM_ENCODER_CURRENT_BITRATE:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_INCOMING_FPS)
    {
        write_log("TOXAV_CALL_COMM_INCOMING_FPS:%d", (int)comm_number);
    }
    else if (comm_value == TOXAV_CALL_COMM_REMOTE_RECORD_DELAY)
    {
        write_log("TOXAV_CALL_COMM_REMOTE_RECORD_DELAY:%d", (int)comm_number);
    }
#endif

    g_latest_telemetry.friend_number = friend_number;
    if ((int)comm_value == TOXAV_CALL_COMM_DECODER_CURRENT_BITRATE) { g_latest_telemetry.toxav_decoder_bitrate = comm_number; }
    if ((int)comm_value == TOXAV_CALL_COMM_NETWORK_ROUND_TRIP_MS) { g_latest_telemetry.toxav_network_roundtrip_ms = comm_number; }
    if ((int)comm_value == TOXAV_CALL_COMM_PLAY_BUFFER_ENTRIES) { g_latest_telemetry.toxav_play_buffer_entries = (int)comm_number; }
    if ((int)comm_value == TOXAV_CALL_COMM_INCOMING_FPS) { g_latest_telemetry.toxav_incoming_fps = comm_number; }

    TOX_ERR_FRIEND_QUERY error3;
    TOX_ERR_FRIEND_QUERY error4;
    bool res_get_name = false;
    uint8_t *f_name = NULL;
    Tox *t = toxav_get_tox(av);
    size_t name_len = tox_friend_get_name_size(t, friend_number, &error3);
    if (error3 == 0)
    {
        Tox_Err_Friend_Query err_tc;
        Tox_Connection tc = tox_friend_get_connection_status(t, friend_number, &err_tc);

        char *tc_str = "TCP";
        if (tc == TOX_CONNECTION_UDP)
        {
            tc_str = "UDP";
        }

        if (name_len > 0)
        {
            f_name = calloc(1, name_len);
            if (f_name)
            {
                res_get_name = tox_friend_get_name(t, friend_number, f_name, &error4);
                if (error4 == TOX_ERR_FRIEND_QUERY_OK)
                {
                    snprintf(g_latest_telemetry.status_message, sizeof(g_latest_telemetry.status_message), 
                             "CON: %s CALLER: %s", tc_str, f_name);
                }
                free(f_name);
            }
        }
        else
        {                
            snprintf(g_latest_telemetry.status_message, sizeof(g_latest_telemetry.status_message), 
                     "CON: %s CALLER: ???", tc_str);
        }
    }
    // Explicitly force null-termination at the very end of the array
    g_latest_telemetry.status_message[sizeof(g_latest_telemetry.status_message) - 1] = '\0';
}


// Python will poll this function to copy the telemetry values out
EXPORT int get_latest_telemetry(uint32_t *out_friend,
            int64_t *toxav_decoder_bitrate,
            int64_t *toxav_network_roundtrip_ms,
            int32_t *toxav_play_buffer_entries,
            int64_t *toxav_incoming_fps,
            char* out_string) {

    if (!is_streaming_active)
    {
        return 0;
    }

    // write_log("get_latest_telemetry ...");
    
    // Feed the stored variables into Python's reference pointers
    *out_friend = g_latest_telemetry.friend_number;

    *toxav_decoder_bitrate = g_latest_telemetry.toxav_decoder_bitrate;
    *toxav_network_roundtrip_ms = g_latest_telemetry.toxav_network_roundtrip_ms;
    *toxav_play_buffer_entries = g_latest_telemetry.toxav_play_buffer_entries;
    *toxav_incoming_fps = g_latest_telemetry.toxav_incoming_fps;

    strcpy(out_string, g_latest_telemetry.status_message);

    return 1; // Return 1 to signify new data is ready
}




EXPORT int start_tox_service() {
    if (g_loop_running) {
        write_log("tox already running");
        return 0; // Loop already active
    }

    write_log("trying to start tox ...");
    
    if (!global_tox) {
        write_log("start tox");
        init(g_profile_dir);
    }

    // --------- Tox callbacks --------- 
    tox_callback_friend_request(global_tox, friend_request_cb);
    tox_callback_friend_status(global_tox, on_tox_friend_status);
    tox_callback_friend_name(global_tox, friend_name_cb);

#ifdef TOX_HAVE_TOXUTIL
    tox_utils_callback_self_connection_status(global_tox, self_connection_status_cb);
    tox_callback_self_connection_status(global_tox, tox_utils_self_connection_status_cb);
    tox_utils_callback_friend_connection_status(global_tox, friendlist_onConnectionChange);
    tox_callback_friend_connection_status(global_tox, tox_utils_friend_connection_status_cb);
    tox_callback_friend_lossless_packet(global_tox, tox_utils_friend_lossless_packet_cb);
#else
    tox_callback_self_connection_status(global_tox, self_connection_status_cb);
    tox_callback_friend_connection_status(global_tox, friendlist_onConnectionChange);
#endif
    write_log("set callbacks");
    // --------- Tox callbacks --------- 
    
    // --------- ToxAV callbacks --------- 
    toxav_callback_call(global_toxav, t_toxav_call_cb, NULL);
    toxav_callback_call_state(global_toxav, t_toxav_call_state_cb, NULL);
    toxav_callback_bit_rate_status(global_toxav, t_toxav_bit_rate_status_cb, NULL);
    toxav_callback_video_receive_frame(global_toxav, t_toxav_receive_video_frame_cb, NULL);
    toxav_callback_video_receive_frame_pts(global_toxav, t_toxav_receive_video_frame_pts_cb, NULL);
    toxav_callback_video_receive_frame_h264(global_toxav, t_toxav_receive_video_frame_h264_cb, NULL);
    // -----------------
    toxav_callback_audio_receive_frame(global_toxav, t_toxav_receive_audio_frame_cb, NULL);
    toxav_callback_audio_receive_frame_pts(global_toxav, t_toxav_receive_audio_frame_pts_cb, NULL);
#ifdef TOX_HAVE_TOXAV_CALLBACKS_002
    toxav_callback_call_comm(global_toxav, t_toxav_call_comm_cb, NULL);
#endif
    write_log("set av callbacks");
    // --------- ToxAV callbacks --------- 
    
    // Process network endpoints setup
    size_t num_nodes = sizeof(bootstrap_nodes) / sizeof(bootstrap_nodes[0]);
    uint8_t bin_key[TOX_PUBLIC_KEY_SIZE];

    for (size_t i = 0; i < num_nodes; i++) {
        hex_to_bin(bootstrap_nodes[i].key_hex, bin_key);
        
        // 1. Core UDP Bootstrap addition (standard protocol entry)
        tox_bootstrap(global_tox, bootstrap_nodes[i].address, bootstrap_nodes[i].port, bin_key, NULL);
        
        // 2. Core TCP Relay addition (fall-back tunnel wrapper for firewalled networks)
        tox_add_tcp_relay(global_tox, bootstrap_nodes[i].address, bootstrap_nodes[i].port, bin_key, NULL);
    }
    write_log("bootstrap");

    g_loop_running = true;

    native_start_video_stream(get_stream_url());
    write_log("native_start_video_stream");

    // Spawn background processing loop thread
#if defined(_WIN32) || defined(_WIN64)
    g_worker_thread = CreateThread(NULL, 0, tox_worker_loop, NULL, 0, NULL);
    if (g_worker_thread == NULL) {
        g_loop_running = false;
        return -1;
    }
    #if defined(_MSC_VER) && (WINVER >= 0x0A00)
        SetThreadDescription(g_worker_thread, L"tox_it");
    #endif
#else
    if (pthread_create(&g_worker_thread, NULL, tox_worker_loop, NULL) != 0) {
        g_loop_running = false;
        return -1;
    }
#endif
    write_log("started tox thread");

    gav_loop_running = true;

    // Spawn background toxav processing loop thread
#if defined(_WIN32) || defined(_WIN64)
    gav_worker_thread = CreateThread(NULL, 0, toxav_worker_loop, NULL, 0, NULL);
    if (gav_worker_thread == NULL) {
        gav_loop_running = false;
        return -1;
    }
    #if defined(_MSC_VER) && (WINVER >= 0x0A00)
        SetThreadDescription(gav_worker_thread, L"toxav_it");
    #endif
#else
    if (pthread_create(&gav_worker_thread, NULL, toxav_worker_loop, NULL) != 0) {
        gav_loop_running = false;
        return -1;
    }
#endif
    write_log("started toxav thread");

    gava_loop_running = true;

    // Spawn background toxav processing loop thread
#if defined(_WIN32) || defined(_WIN64)
    gava_worker_thread = CreateThread(NULL, 0, toxava_worker_loop, NULL, 0, NULL);
    if (gava_worker_thread == NULL) {
        gava_loop_running = false;
        return -1;
    }
    #if defined(_MSC_VER) && (WINVER >= 0x0A00)
        SetThreadDescription(gava_worker_thread, L"toxava_it");
    #endif
#else
    if (pthread_create(&gava_worker_thread, NULL, toxava_worker_loop, NULL) != 0) {
        gava_loop_running = false;
        return -1;
    }
#endif
    write_log("started toxava thread");


    return 1;
}

EXPORT int stop_tox_service() {
    write_log("stop_tox_service:001");
    if (!g_loop_running) {
        write_log("tox already stopped");
        return 0; 
    }
    
    write_log("trying to stop tox ...");
    
    native_stop_video_stream(get_stream_url());
    
    gav_loop_running = false;

#if defined(_WIN32) || defined(_WIN64)
    WaitForSingleObject(gav_worker_thread, INFINITE);
    CloseHandle(gav_worker_thread);
#else
    pthread_join(gav_worker_thread, NULL);
#endif

    gava_loop_running = false;

#if defined(_WIN32) || defined(_WIN64)
    WaitForSingleObject(gava_worker_thread, INFINITE);
    CloseHandle(gava_worker_thread);
#else
    pthread_join(gava_worker_thread, NULL);
#endif

    g_loop_running = false;

#if defined(_WIN32) || defined(_WIN64)
    WaitForSingleObject(g_worker_thread, INFINITE);
    CloseHandle(g_worker_thread);
#else
    pthread_join(g_worker_thread, NULL);
#endif

    if (global_tox) {
        update_savedata_file(global_tox);

        ToxAV *tox_av_global_copy = global_toxav;
        global_toxav = NULL;

        Tox *tox_global_copy = global_tox;
        global_tox = NULL; 

        toxav_kill(tox_av_global_copy);
        write_log("kill toxav");

#ifdef TOX_HAVE_TOXUTIL
        tox_utils_kill(tox_global_copy);
#else
        tox_kill(tox_global_copy);
#endif
    }
    write_log("kill tox");
    
    return 1;
}

#ifdef __cplusplus
}
#endif
