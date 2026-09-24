// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import kotlin.math.min

/**
 * Circular digital directional control. A single finger selects one of eight
 * angular regions; the four diagonals emit two simultaneous cardinal buttons,
 * never a synthetic one. Geometry comes from the canonical
 * [NativeInputActions.circularDirections] shared with the Phone Controller.
 */
class NativeCircularDpad(
    context: Context,
    private val onDirections: (Set<Int>) -> Unit,
) : View(context) {
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2f; color = NativePlayerUi.BORDER_COLOR }
    private val arrow = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; color = NativePlayerUi.TEXT_COLOR; isFakeBoldText = true }
    private val bounds = RectF()

    private var pointerId = -1
    private var region: String? = null
    private var pressed: Set<Int> = emptySet()
    private var currentActions: Set<String> = emptySet()

    init {
        isClickable = true
        isFocusable = true
    }

    /** Release the control and every direction it holds. Safe to call repeatedly. */
    fun release() {
        pointerId = -1
        region = null
        currentActions = emptySet()
        if (pressed.isNotEmpty()) onDirections(emptySet())
        pressed = emptySet()
        invalidate()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                if (pointerId >= 0) return true
                pointerId = event.getPointerId(event.actionIndex)
                update(event)
            }
            MotionEvent.ACTION_MOVE -> {
                if (pointerId < 0) return true
                val index = event.findPointerIndex(pointerId)
                if (index >= 0) update(event, index)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> release()
            MotionEvent.ACTION_POINTER_UP -> {
                if (event.getPointerId(event.actionIndex) == pointerId) release()
            }
        }
        return true
    }

    private fun update(event: MotionEvent, index: Int = event.actionIndex) {
        val radius = min(width, height) / 2f
        if (radius <= 0f) return
        val dx = (event.getX(index) - width / 2f) / radius
        val dy = (event.getY(index) - height / 2f) / radius
        val result = NativeInputActions.circularDirections(dx, dy, region)
        region = result.region
        currentActions = result.actions
        val ids = NativeInputActions.pressedCardinals(result.actions)
        if (ids != pressed) {
            pressed = ids
            onDirections(ids)
        }
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = MeasureSpec.getSize(widthMeasureSpec)
        val height = MeasureSpec.getSize(heightMeasureSpec)
        val size = min(width, height)
        super.onMeasure(
            MeasureSpec.makeMeasureSpec(size, MeasureSpec.EXACTLY),
            MeasureSpec.makeMeasureSpec(size, MeasureSpec.EXACTLY),
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val radius = min(width, height) / 2f
        val cx = width / 2f
        val cy = height / 2f
        bounds.set(cx - radius + 1f, cy - radius + 1f, cx + radius - 1f, cy + radius - 1f)
        canvas.drawCircle(cx, cy, radius - 1f, fill.apply { color = NativePlayerUi.CONTROL_COLOR })
        canvas.drawCircle(cx, cy, radius - 1f, stroke)
        canvas.drawCircle(cx, cy, radius * 0.3f, fill.apply { color = 0x55201933 })
        arrow.textSize = radius * 0.42f
        // Canvas 0 degrees is east and grows clockwise (screen coordinates).
        val wedges = listOf(
            "UP" to 225f, "RIGHT" to 315f, "DOWN" to 45f, "LEFT" to 135f,
        )
        val labels = mapOf("UP" to "▲", "DOWN" to "▼", "LEFT" to "◀", "RIGHT" to "▶")
        for ((action, start) in wedges) {
            fill.color = if (action in currentActions) 0xcc8b5cf6.toInt() else 0x332f2a44
            canvas.drawArc(bounds, start, 90f, true, fill)
        }
        canvas.drawCircle(cx, cy, radius - 1f, stroke)
        canvas.drawCircle(cx, cy, radius * 0.3f, stroke)
        val offset = radius * 0.55f
        val baseline = arrow.textSize / 2.5f
        canvas.drawText(labels.getValue("UP"), cx, cy - offset + baseline, arrow)
        canvas.drawText(labels.getValue("DOWN"), cx, cy + offset + baseline, arrow)
        canvas.drawText(labels.getValue("LEFT"), cx - offset, cy + baseline, arrow)
        canvas.drawText(labels.getValue("RIGHT"), cx + offset, cy + baseline, arrow)
    }
}
