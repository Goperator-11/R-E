/*
 * rs_bench.c - GF(256) Reed-Solomon erasure-coding throughput, in C.
 *
 * The python encoder in afec/rs.py is correct but ~100x slower than a real
 * implementation, and the project has been carrying "a C implementation would
 * be 100x faster" as an ASSUMPTION.  This measures it instead.
 *
 * Same construction as afec/rs.py: systematic code, Cauchy generator matrix
 * over GF(256) with the AES/QR polynomial 0x11d.
 *
 * Build:  gcc -O3 -march=native -o rs_bench rs_bench.c
 * Run:    ./rs_bench <k> <r> <symbol_bytes> <blocks>
 * Prints one JSON line.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static unsigned char gf_exp[512];
static unsigned char gf_log[256];
static unsigned char gf_mul_tab[256][256];

static void gf_init(void)
{
    int x = 1;
    for (int i = 0; i < 255; i++) {
        gf_exp[i] = (unsigned char)x;
        gf_log[x] = (unsigned char)i;
        x <<= 1;
        if (x & 0x100)
            x ^= 0x11d;
    }
    for (int i = 255; i < 512; i++)
        gf_exp[i] = gf_exp[i - 255];
    gf_log[0] = 0;
    for (int a = 0; a < 256; a++)
        for (int b = 0; b < 256; b++)
            gf_mul_tab[a][b] =
                (a == 0 || b == 0) ? 0
                                   : gf_exp[gf_log[a] + gf_log[b]];
}

static unsigned char gf_mul(unsigned char a, unsigned char b)
{
    return (a == 0 || b == 0) ? 0 : gf_exp[gf_log[a] + gf_log[b]];
}

static unsigned char gf_inv(unsigned char a)
{
    return gf_exp[255 - gf_log[a]];
}

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(int argc, char **argv)
{
    int k = argc > 1 ? atoi(argv[1]) : 32;
    int r = argc > 2 ? atoi(argv[2]) : 8;
    int sym = argc > 3 ? atoi(argv[3]) : 1200;
    int blocks = argc > 4 ? atoi(argv[4]) : 2000;

    if (k <= 0 || r <= 0 || k + r > 255 || sym <= 0) {
        fprintf(stderr, "bad args\n");
        return 2;
    }
    gf_init();

    /* Cauchy generator: G[j][i] = 1 / (x_j ^ y_i), disjoint x and y. */
    unsigned char *G = malloc((size_t)r * k);
    for (int j = 0; j < r; j++)
        for (int i = 0; i < k; i++) {
            unsigned char xj = (unsigned char)(j + k);
            unsigned char yi = (unsigned char)i;
            G[(size_t)j * k + i] = gf_inv((unsigned char)(xj ^ yi));
        }

    unsigned char *src = malloc((size_t)k * sym);
    unsigned char *rep = malloc((size_t)r * sym);
    for (size_t i = 0; i < (size_t)k * sym; i++)
        src[i] = (unsigned char)(i * 2654435761u >> 13);

    /* ---- encode: repair[j] = sum_i G[j][i] * src[i] ---- */
    double t0 = now_s();
    unsigned long long checksum = 0;
    for (int b = 0; b < blocks; b++) {
        memset(rep, 0, (size_t)r * sym);
        for (int j = 0; j < r; j++) {
            unsigned char *dst = rep + (size_t)j * sym;
            for (int i = 0; i < k; i++) {
                const unsigned char *row = gf_mul_tab[G[(size_t)j * k + i]];
                const unsigned char *s = src + (size_t)i * sym;
                for (int t = 0; t < sym; t++)
                    dst[t] ^= row[s[t]];
            }
        }
        checksum += rep[0] + rep[sym - 1];
        src[b % ((size_t)k * sym)] ^= 1;   /* defeat over-eager hoisting */
    }
    double enc_s = now_s() - t0;

    /* ---- pure XOR parity (r = 1), what the handshake shield uses ----
     * NOTE: the input must be mutated every iteration or the compiler hoists
     * the whole loop out and reports an impossible ~100 GB/s.  That actually
     * happened on the first run of this benchmark. */
    double t1 = now_s();
    for (int b = 0; b < blocks; b++) {
        unsigned char *dst = rep;
        memcpy(dst, src, sym);
        for (int i = 1; i < k; i++) {
            const unsigned char *s = src + (size_t)i * sym;
            for (int t = 0; t < sym; t++)
                dst[t] ^= s[t];
        }
        checksum += dst[0] + dst[sym - 1];
        src[(size_t)(b * 7919) % ((size_t)k * sym)] ^= 1;
    }
    double xor_s = now_s() - t1;

    double enc_ms_block = enc_s * 1000.0 / blocks;
    double src_mb = (double)k * sym / 1e6;
    printf("{\"k\":%d,\"r\":%d,\"symbol_bytes\":%d,\"blocks\":%d,"
           "\"encode_ms_per_block\":%.6f,"
           "\"encode_ms_per_repair_symbol\":%.6f,"
           "\"encode_MBps_source\":%.2f,"
           "\"xor_parity_ms_per_block\":%.6f,"
           "\"xor_parity_MBps\":%.2f,"
           "\"checksum\":%llu}\n",
           k, r, sym, blocks,
           enc_ms_block,
           enc_ms_block / r,
           src_mb / (enc_s / blocks),
           xor_s * 1000.0 / blocks,
           src_mb / (xor_s / blocks),
           checksum);

    free(G);
    free(src);
    free(rep);
    return 0;
}
