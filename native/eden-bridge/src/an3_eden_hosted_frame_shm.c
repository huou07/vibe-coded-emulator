// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// POSIX shared-memory transport for the hosted-frame ring. Pure C; no GPU.
#include "an3_eden_hosted_frame_shm.h"

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__APPLE__) && !defined(_POSIX_SHARED_MEMORY_OBJECTS)
#error "POSIX shared memory is required for the hosted-frame transport"
#endif

static int init_process_mutex(pthread_mutex_t* mutex) {
    pthread_mutexattr_t attr;
    if (pthread_mutexattr_init(&attr) != 0) {
        return -1;
    }
    int rc = pthread_mutexattr_setpshared(&attr, PTHREAD_PROCESS_SHARED);
    if (rc == 0) {
        rc = pthread_mutex_init(mutex, &attr);
    }
    pthread_mutexattr_destroy(&attr);
    return rc == 0 ? 0 : -1;
}

int an3_eden_hosted_shm_create(const char* name, an3_eden_hosted_shm** out) {
    if (name == NULL || out == NULL) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    *out = NULL;
    const int fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0) {
        return AN3_EDEN_HOSTED_ERR_BUSY;
    }
    const size_t size = sizeof(an3_eden_hosted_shm);
    if (ftruncate(fd, (off_t)size) != 0) {
        close(fd);
        shm_unlink(name);
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    void* address = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (address == MAP_FAILED) {
        shm_unlink(name);
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    an3_eden_hosted_shm* shm = (an3_eden_hosted_shm*)address;
    memset(shm, 0, size);
    if (init_process_mutex(&shm->mutex) != 0) {
        munmap(address, size);
        shm_unlink(name);
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    shm->magic = AN3_EDEN_HOSTED_SHM_MAGIC;
    shm->struct_size = (uint32_t)size;
    shm->protocol_version = AN3_EDEN_HOSTED_PROTOCOL_VERSION;
    const int ring_rc =
        an3_eden_hosted_ring_init(&shm->ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
    if (ring_rc != AN3_EDEN_HOSTED_OK) {
        munmap(address, size);
        shm_unlink(name);
        return ring_rc;
    }
    *out = shm;
    return AN3_EDEN_HOSTED_OK;
}

int an3_eden_hosted_shm_attach(const char* name, an3_eden_hosted_shm** out) {
    if (name == NULL || out == NULL) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    *out = NULL;
    const int fd = shm_open(name, O_RDWR, 0);
    if (fd < 0) {
        return AN3_EDEN_HOSTED_ERR_EMPTY;
    }
    struct stat info;
    const size_t size = sizeof(an3_eden_hosted_shm);
    if (fstat(fd, &info) != 0 || info.st_size < (off_t)size) {
        close(fd);
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    void* address = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (address == MAP_FAILED) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    an3_eden_hosted_shm* shm = (an3_eden_hosted_shm*)address;
    if (shm->magic != AN3_EDEN_HOSTED_SHM_MAGIC || shm->struct_size != (uint32_t)size ||
        shm->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        munmap(address, size);
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    *out = shm;
    return AN3_EDEN_HOSTED_OK;
}

void an3_eden_hosted_shm_detach(an3_eden_hosted_shm* shm) {
    if (shm != NULL) {
        munmap((void*)shm, sizeof(an3_eden_hosted_shm));
    }
}

void an3_eden_hosted_shm_unlink(const char* name) {
    if (name != NULL) {
        shm_unlink(name);
    }
}

int an3_eden_hosted_shm_lock(an3_eden_hosted_shm* shm) {
    if (shm == NULL) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    return pthread_mutex_lock(&shm->mutex) == 0 ? AN3_EDEN_HOSTED_OK
                                                : AN3_EDEN_HOSTED_ERR_ARGUMENT;
}

int an3_eden_hosted_shm_trylock(an3_eden_hosted_shm* shm) {
    if (shm == NULL) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    return pthread_mutex_trylock(&shm->mutex) == 0 ? AN3_EDEN_HOSTED_OK
                                                   : AN3_EDEN_HOSTED_ERR_BUSY;
}

int an3_eden_hosted_shm_unlock(an3_eden_hosted_shm* shm) {
    if (shm == NULL) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    return pthread_mutex_unlock(&shm->mutex) == 0 ? AN3_EDEN_HOSTED_OK
                                                  : AN3_EDEN_HOSTED_ERR_ARGUMENT;
}
