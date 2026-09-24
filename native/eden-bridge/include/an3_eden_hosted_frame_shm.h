// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Cross-process transport for the versioned hosted-frame ring.
//
// The producer (the Eden companion) creates a POSIX shared-memory object that
// holds the `an3_eden_hosted_ring` plus a process-shared mutex, and prints its
// name. The AN3 host attaches to the same object and consumes descriptors. The
// ring ABI (an3_eden_hosted_frame.h) is unchanged; this file only adds the
// placement, a magic/size/version header for safe attachment, and locking.
//
// It carries only opaque IOSurface ids and metadata: no pointers, no pixels.
#ifndef AN3_EDEN_HOSTED_FRAME_SHM_H
#define AN3_EDEN_HOSTED_FRAME_SHM_H

#include <pthread.h>
#include <stddef.h>
#include <stdint.h>

#include "an3_eden_hosted_frame.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 'AN3H'. Bump with the layout. */
#define AN3_EDEN_HOSTED_SHM_MAGIC 0x414E3348u

/* A process-shared mutex guards the ring. Keep names short: macOS limits a
 * POSIX shared-memory name segment to PSHMNAMLEN (31) characters. */
typedef struct {
    uint32_t magic;
    uint32_t struct_size;
    uint32_t protocol_version;
    uint32_t reserved;
    pthread_mutex_t mutex;
    an3_eden_hosted_ring ring;
} an3_eden_hosted_shm;

/* Create and initialize a new shared-memory ring. Fails if `name` already
 * exists (O_EXCL) or on any OS error. */
int an3_eden_hosted_shm_create(const char* name, an3_eden_hosted_shm** out);

/* Attach to an existing ring created by `an3_eden_hosted_shm_create`. Validates
 * magic, size and protocol version before returning it. */
int an3_eden_hosted_shm_attach(const char* name, an3_eden_hosted_shm** out);

/* Unmap a ring obtained from create/attach. Does not unlink the name. */
void an3_eden_hosted_shm_detach(an3_eden_hosted_shm* shm);

/* Remove the shared-memory name so no new process can attach. An already
 * attached consumer keeps its mapping. */
void an3_eden_hosted_shm_unlink(const char* name);

int an3_eden_hosted_shm_lock(an3_eden_hosted_shm* shm);
int an3_eden_hosted_shm_trylock(an3_eden_hosted_shm* shm);
int an3_eden_hosted_shm_unlock(an3_eden_hosted_shm* shm);

#ifdef __cplusplus
}
#endif

#endif /* AN3_EDEN_HOSTED_FRAME_SHM_H */
