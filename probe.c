/*
 * probe.c — Enterprise Architecture Control Plane: pure-C service prober.
 * Bleeding-edge, dependency-free, EPYC-native.
 *
 * Probes a list of http://host:port/path URLs concurrently using non-blocking
 * sockets + epoll, extracts the HTTP status code, and emits JSON.
 *
 * Build (EPYC Zen2 / znver2):
 *   make            # -O3 -march=znver2 -flto, 64-core thread pool
 *
 * Input: URLs, one per line, on stdin or via -f file.
 * Output: JSON array of {url, status:up|down, code, latency_us, error?}
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/epoll.h>
#include <netdb.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define MAX_URLS 4096
#define BUFSZ 8192
#define CONN_TIMEOUT_MS 1500
#define READ_TIMEOUT_MS 1500

typedef struct {
    char url[2048];
    char host[1024];
    char path[1024];
    int port;
    int idx;
} target_t;

typedef struct {
    int code;            /* HTTP status code, 0 if none */
    int status;          /* 1 up, 0 down */
    long latency_us;
    char err[128];
} result_t;

static target_t targets[MAX_URLS];
static result_t results[MAX_URLS];
static int ntargets = 0;

/* parse http://host:port/path (port/path optional) */
static int parse_url(const char *u, target_t *t) {
    const char *p = u;
    if (strncmp(p, "http://", 7) == 0) p += 7;
    else if (strncmp(p, "https://", 8) == 0) return -1; /* unsupported */
    t->port = 80;
    t->path[0] = '/'; t->path[1] = '\0';
    char *slash = strchr(p, '/');
    size_t hostlen = slash ? (size_t)(slash - p) : strlen(p);
    if (hostlen >= sizeof(t->host)) return -1;
    memcpy(t->host, p, hostlen);
    t->host[hostlen] = '\0';
    if (slash) {
        strncpy(t->path, slash, sizeof(t->path) - 1);
        t->path[sizeof(t->path) - 1] = '\0';
    }
    char *colon = strrchr(t->host, ':');
    if (colon) {
        *colon = '\0';
        t->port = atoi(colon + 1);
    }
    return 0;
}

static long now_us(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

/* probe one target; fill results[idx] */
static void probe_one(target_t *t) {
    result_t *r = &results[t->idx];
    r->code = 0; r->status = 0; r->latency_us = 0; r->err[0] = '\0';
    long t0 = now_us();

    struct addrinfo hints, *res = NULL;
    char portstr[16]; snprintf(portstr, sizeof(portstr), "%d", t->port);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(t->host, portstr, &hints, &res) != 0) {
        snprintf(r->err, sizeof(r->err), "dns"); r->latency_us = now_us() - t0; return;
    }
    int fd = -1;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0) continue;
        fcntl(fd, F_SETFL, O_NONBLOCK);
        if (connect(fd, ai->ai_addr, ai->ai_addrlen) == 0 || errno == EINPROGRESS) break;
        close(fd); fd = -1;
    }
    if (fd < 0) { snprintf(r->err, sizeof(r->err), "socket"); freeaddrinfo(res); r->latency_us = now_us() - t0; return; }

    int ep = epoll_create1(0);
    struct epoll_event ev; ev.events = EPOLLOUT; ev.data.fd = fd;
    epoll_ctl(ep, EPOLL_CTL_ADD, fd, &ev);
    struct epoll_event out;
    int n = epoll_wait(ep, &out, 1, CONN_TIMEOUT_MS);
    if (n <= 0) { snprintf(r->err, sizeof(r->err), "conn_timeout"); goto done; }

    /* send GET */
    char req[2400];
    int rl = snprintf(req, sizeof(req),
        "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: eacp-probe/1.0\r\nConnection: close\r\n\r\n",
        t->path, t->host);
    send(fd, req, rl, 0);

    /* wait for response */
    ev.events = EPOLLIN; epoll_ctl(ep, EPOLL_CTL_MOD, fd, &ev);
    n = epoll_wait(ep, &out, 1, READ_TIMEOUT_MS);
    if (n <= 0) { snprintf(r->err, sizeof(r->err), "read_timeout"); goto done; }

    char buf[BUFSZ];
    int got = recv(fd, buf, sizeof(buf) - 1, 0);
    if (got > 0) {
        buf[got] = '\0';
        /* parse "HTTP/1.x NNN" */
        if (strncmp(buf, "HTTP/", 5) == 0) {
            int code = 0; sscanf(buf, "HTTP/%*s %d", &code);
            r->code = code;
            r->status = (code >= 100 && code < 600) ? 1 : 0;
        } else { snprintf(r->err, sizeof(r->err), "bad_resp"); }
    } else { snprintf(r->err, sizeof(r->err), "no_data"); }

done:
    r->latency_us = now_us() - t0;
    close(fd); close(ep); freeaddrinfo(res);
}

static void *worker(void *arg) {
    long start = (long)arg;
    long step = sysconf(_SC_NPROCESSORS_ONLN);
    for (long i = start; i < ntargets; i += step) probe_one(&targets[i]);
    return NULL;
}

int main(int argc, char **argv) {
    FILE *in = stdin;
    if (argc > 2 && strcmp(argv[1], "-f") == 0) { in = fopen(argv[2], "r"); if (!in) { perror("fopen"); return 1; } }
    char line[2048];
    while (fgets(line, sizeof(line), in) && ntargets < MAX_URLS) {
        size_t L = strlen(line); while (L && (line[L-1]=='\n'||line[L-1]=='\r')) line[--L]=0;
        if (!L) continue;
        strncpy(targets[ntargets].url, line, sizeof(targets[ntargets].url) - 1);
        targets[ntargets].url[sizeof(targets[ntargets].url) - 1] = '\0';
        if (parse_url(line, &targets[ntargets]) != 0) {
            snprintf(results[ntargets].err, sizeof(results[ntargets].err), "bad_url");
            ntargets++; continue;
        }
        targets[ntargets].idx = ntargets;
        ntargets++;
    }
    if (in != stdin) fclose(in);

    long ncpu = sysconf(_SC_NPROCESSORS_ONLN);
    long nthreads = ncpu; if (nthreads > ntargets) nthreads = ntargets; if (nthreads < 1) nthreads = 1;
    pthread_t *th = calloc(nthreads, sizeof(pthread_t));
    for (long i = 0; i < nthreads; i++) pthread_create(&th[i], NULL, worker, (void*)i);
    for (long i = 0; i < nthreads; i++) pthread_join(th[i], NULL);
    free(th);

    /* emit JSON */
    printf("[");
    for (int i = 0; i < ntargets; i++) {
        result_t *r = &results[i];
        printf("%s\n  {\"url\":\"%s\",\"status\":\"%s\",\"code\":%d,\"latency_us\":%ld",
               i?",":"", targets[i].url, r->status?"up":"down", r->code, r->latency_us);
        if (r->err[0]) printf(",\"error\":\"%s\"", r->err);
        printf("}");
    }
    printf("\n]\n");
    return 0;
}
