#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/objects.h>
#include <math.h>

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1.0e6;
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static double pct(double *sorted, int n, double p) {
    if (n <= 0) return 0.0;
    if (n == 1) return sorted[0];
    double idx = (p / 100.0) * (n - 1);
    int lo = (int)idx;
    int hi = lo + 1 < n ? lo + 1 : n - 1;
    double frac = idx - lo;
    return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
}

int main(int argc, char **argv) {
    if (argc < 6) {
        fprintf(stderr,
            "사용법: %s <host> <port> <group> <iters> <warmup> [출력.csv]\n"
            "예:     %s 127.0.0.1 44555 MLKEM768 500 20 out.csv\n",
            argv[0], argv[0]);
        return 2;
    }
    const char *host   = argv[1];
    int         port   = atoi(argv[2]);
    const char *group  = argv[3];
    int         iters  = atoi(argv[4]);
    int         warmup = atoi(argv[5]);
    const char *csv    = (argc > 6) ? argv[6] : NULL;

    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    if (!ctx) { ERR_print_errors_fp(stderr); return 1; }

    SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);
    SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION);

    SSL_CTX_set_verify(ctx, SSL_VERIFY_NONE, NULL);

    SSL_CTX_set_session_cache_mode(ctx, SSL_SESS_CACHE_OFF);
    SSL_CTX_set_options(ctx, SSL_OP_NO_TICKET);

    if (SSL_CTX_set1_groups_list(ctx, group) != 1) {
        fprintf(stderr, "그룹 '%s' 설정 실패 — 이 OpenSSL 빌드가 지원하지 않습니다\n", group);
        ERR_print_errors_fp(stderr);
        SSL_CTX_free(ctx);
        return 1;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof addr);
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(port);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) {
        fprintf(stderr, "잘못된 주소: %s\n", host);
        SSL_CTX_free(ctx);
        return 1;
    }

    int total = warmup + iters;
    double *tcp_ms   = calloc(iters, sizeof(double));
    double *tls_ms   = calloc(iters, sizeof(double));
    double *all_ms   = calloc(iters, sizeof(double));
    if (!tcp_ms || !tls_ms || !all_ms) { perror("calloc"); return 1; }

    FILE *fp = NULL;
    if (csv) {
        fp = fopen(csv, "w");
        if (!fp) { perror("fopen"); return 1; }
        fprintf(fp, "group,iter,tcp_ms,tls_ms,total_ms,status,negotiated_group\n");
    }

    int ok = 0, fail = 0;
    const char *neg_name = "?";

    for (int i = 0; i < total; i++) {
        int is_warmup = (i < warmup);
        double t0 = now_ms();

        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) { perror("socket"); fail++; continue; }

        int one = 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);

        if (connect(fd, (struct sockaddr *)&addr, sizeof addr) != 0) {
            close(fd);
            fail++;
            if (fp && !is_warmup)
                fprintf(fp, "%s,%d,,,,tcp_fail,\n", group, i - warmup);
            continue;
        }
        double t1 = now_ms();

        SSL *ssl = SSL_new(ctx);
        SSL_set_fd(ssl, fd);
        SSL_set_tlsext_host_name(ssl, "localhost");

        int r = SSL_connect(ssl);
        double t2 = now_ms();

        if (r == 1) {
            int nid = SSL_get_negotiated_group(ssl);
            const char *n = OBJ_nid2sn(nid);
            if (n) neg_name = n;

            if (!is_warmup) {
                int k = i - warmup;
                tcp_ms[k] = t1 - t0;
                tls_ms[k] = t2 - t1;
                all_ms[k] = t2 - t0;
                if (fp)
                    fprintf(fp, "%s,%d,%.4f,%.4f,%.4f,ok,%s\n",
                            group, k, tcp_ms[k], tls_ms[k], all_ms[k],
                            n ? n : "?");
            }
            ok++;
        } else {
            fail++;
            if (fp && !is_warmup)
                fprintf(fp, "%s,%d,%.4f,,,tls_fail,\n",
                        group, i - warmup, t1 - t0);
        }

        SSL_free(ssl);
        close(fd);
    }

    if (fp) fclose(fp);

    int n = 0;
    for (int i = 0; i < iters; i++) if (all_ms[i] > 0.0) n++;

    double *s = calloc(n > 0 ? n : 1, sizeof(double));
    int j = 0;
    double sum = 0.0;
    for (int i = 0; i < iters; i++)
        if (all_ms[i] > 0.0) { s[j++] = all_ms[i]; sum += all_ms[i]; }
    qsort(s, n, sizeof(double), cmp_double);

    double mean = n ? sum / n : 0.0;
    double var = 0.0;
    for (int i = 0; i < n; i++) var += (s[i] - mean) * (s[i] - mean);
    double sd = n > 1 ? sqrt(var / (n - 1)) : 0.0;

    printf("group=%-18s negotiated=%-18s n=%d  fail=%d  실패율=%.2f%%\n",
           group, neg_name, n, fail,
           (ok + fail) ? 100.0 * fail / (ok + fail) : 0.0);
    if (n) {
        printf("  총 HCT(ms)  mean=%.3f  sd=%.3f  p50=%.3f  p95=%.3f  p99=%.3f  min=%.3f  max=%.3f\n",
               mean, sd, pct(s, n, 50), pct(s, n, 95), pct(s, n, 99), s[0], s[n - 1]);
    }

    free(s); free(tcp_ms); free(tls_ms); free(all_ms);
    SSL_CTX_free(ctx);
    return 0;
}
