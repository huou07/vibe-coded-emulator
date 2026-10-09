// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.view.MotionEvent
import android.view.View

/** A circular surface and movable circular thumb; owns one pointer until release. */
class NativeAnalogStick(context: Context, private val input: (Float, Float) -> Unit) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var axis = NativePlayerUi.Axis()
    private var pointer = MotionEvent.INVALID_POINTER_ID

    init { contentDescription = "Analog Joystick"; isClickable = true }

    fun release() {
        pointer = MotionEvent.INVALID_POINTER_ID
        axis = NativePlayerUi.Axis()
        input(0f, 0f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val radius = (minOf(width, height) / 2f - resources.displayMetrics.density).coerceAtLeast(1f)
        val cx = width / 2f; val cy = height / 2f
        paint.style = Paint.Style.FILL; paint.color = NativePlayerUi.CONTROL_COLOR
        canvas.drawCircle(cx, cy, radius, paint)
        paint.style = Paint.Style.STROKE; paint.strokeWidth = 1.5f * resources.displayMetrics.density
        paint.color = NativePlayerUi.BORDER_COLOR; canvas.drawCircle(cx, cy, radius, paint)
        paint.style = Paint.Style.FILL; paint.color = NativePlayerUi.THUMB_COLOR
        val travel = radius * NativePlayerUi.TRAVEL_RATIO
        canvas.drawCircle(cx + axis.x * travel, cy + axis.y * travel,
            radius * NativePlayerUi.THUMB_RADIUS_RATIO, paint)
    }

    private fun update(event: MotionEvent) {
        val index = event.findPointerIndex(pointer)
        if (index < 0) { release(); return }
        val travel = (minOf(width, height) / 2f * NativePlayerUi.TRAVEL_RATIO).coerceAtLeast(1f)
        axis = NativePlayerUi.normalize((event.getX(index) - width / 2f) / travel,
            (event.getY(index) - height / 2f) / travel)
        input(axis.x, axis.y)
        invalidate()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                pointer = event.getPointerId(event.actionIndex)
                parent?.requestDisallowInterceptTouchEvent(true)
                update(event)
            }
            MotionEvent.ACTION_MOVE -> update(event)
            MotionEvent.ACTION_POINTER_UP -> if (event.getPointerId(event.actionIndex) == pointer) release()
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                release(); parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
        return true
    }

    override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
        super.onWindowFocusChanged(hasWindowFocus)
        if (!hasWindowFocus) release()
    }
    override fun onDetachedFromWindow() { release(); super.onDetachedFromWindow() }
}
