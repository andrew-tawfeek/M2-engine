#define _GNU_SOURCE
#include <gc/gc.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

/* Observe the two GCstats calls in the unchanged slow-gc wrapper.
 * Optional interventions happen BEFORE the first snapshot / internal timer. */
static int calls;
static double wall(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
static void snapshot(const char *phase) {
    struct rusage r; getrusage(RUSAGE_SELF, &r);
    const char *path = getenv("PROFILE_LOG");
    if (!path) _exit(110);
    FILE *f = fopen(path, "a"); if (!f) _exit(111);
    fprintf(f, "%s|%.9f|%.9f|%.9f|%ld|%ld|%ld|%ld|%ld\n", phase, wall(),
      r.ru_utime.tv_sec + r.ru_utime.tv_usec * 1e-6,
      r.ru_stime.tv_sec + r.ru_stime.tv_usec * 1e-6,
      r.ru_minflt, r.ru_majflt, r.ru_maxrss, r.ru_nvcsw, r.ru_nivcsw);
    fclose(f);
}
static void control(const char *command) {
    const char *ctl = getenv("PROFILE_CTL"), *ack = getenv("PROFILE_ACK");
    if (!ctl) return;
    int fd = open(ctl, O_WRONLY); if (fd < 0) _exit(112);
    int af = open(ack, O_RDONLY); if (af < 0) _exit(113);
    if (write(fd, command, strlen(command)) < 0) _exit(114);
    char c; while (read(af, &c, 1) == 1 && c != '\n') {}
    close(af); close(fd);
}
__attribute__((constructor)) static void initialize(void) {
    char executable[4096];
    ssize_t n = readlink("/proc/self/exe", executable, sizeof(executable)-1);
    if (n < 0) return;
    executable[n] = 0;
    const char *base = strrchr(executable, '/');
    if (!base || strcmp(base+1, "M2-binary")) return;
    GC_start_performance_measurement();
    snapshot("constructor");
}
size_t GC_get_prof_stats(struct GC_prof_stats_s *stats, size_t bytes) {
    static size_t (*real_stats)(struct GC_prof_stats_s *, size_t);
    if (!real_stats) real_stats = dlsym(RTLD_NEXT, "GC_get_prof_stats");
    ++calls;
    if (calls == 1) {
        snapshot("setup-start");
        const char *policy = getenv("PROFILE_POLICY");
        if (policy && !strcmp(policy, "late-off")) GC_disable();
        if (policy && !strcmp(policy, "reserve")) {
            size_t n = (size_t)strtoull(getenv("PROFILE_RESERVE_MIB"), NULL, 10) * 1024 * 1024;
            void *p = GC_malloc_atomic(n);
            if (!p) _exit(115);
            memset(p, 0x5a, n); /* Commit physical pages, then return blocks for reuse. */
            GC_free(p);
        }
        control("enable\n");
        snapshot("begin");
    }
    size_t result = real_stats(stats, bytes);
    if (calls == 2) { snapshot("end"); control("disable\n"); }
    return result;
}
