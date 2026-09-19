// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  const parse = value => (value || "").split(",").map(Number).filter(Number.isFinite);

  const draw = canvas => {
    const primary = parse(canvas.dataset.series);
    const secondary = parse(canvas.dataset.series2);
    if (primary.length < 2 && secondary.length < 2) return;
    const series = [
      {values: primary, color: canvas.dataset.color || "#a855f7", fill: true},
      {values: secondary, color: canvas.dataset.color2 || "#22d3ee", fill: false},
    ].filter(item => item.values.length >= 2);
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const ratio = Math.min(2, devicePixelRatio || 1);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const pad = {left: 12, right: 10, top: 16, bottom: 10};
    const all = series.flatMap(item => item.values);
    const peak = Math.max(...all);
    const low = Math.min(...all);
    const max = peak * 1.08;
    const min = low * .82;
    const span = Math.max(1, max - min);
    const point = (value, index, length) => ({
      x: pad.left + index * ((width - pad.left - pad.right) / (length - 1)),
      y: pad.top + (max - value) * ((height - pad.top - pad.bottom) / span)
    });
    context.lineWidth = 1;
    context.strokeStyle = "rgba(164,159,181,.16)";
    context.setLineDash([2, 4]);
    for (let row = 0; row < 5; row += 1) {
      const y = pad.top + row * ((height - pad.top - pad.bottom) / 4);
      context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    }
    context.setLineDash([]);
    series.forEach((item, order) => {
      const points = item.values.map((value, index) => point(value, index, item.values.length));
      if (item.fill) {
        const fill = context.createLinearGradient(0, pad.top, 0, height);
        fill.addColorStop(0, `${item.color}55`);
        fill.addColorStop(1, `${item.color}00`);
        context.beginPath();
        points.forEach((p, index) => { if (index) context.lineTo(p.x, p.y); else context.moveTo(p.x, p.y); });
        context.lineTo(width - pad.right, height - pad.bottom);
        context.lineTo(pad.left, height - pad.bottom);
        context.closePath(); context.fillStyle = fill; context.fill();
      }
      context.beginPath();
      points.forEach((p, index) => { if (index) context.lineTo(p.x, p.y); else context.moveTo(p.x, p.y); });
      context.strokeStyle = item.color;
      context.lineWidth = order === 0 ? 2.5 : 2;
      context.globalAlpha = order === 0 ? 1 : .92;
      context.stroke();
      context.globalAlpha = 1;
      context.fillStyle = item.color;
      points.forEach(p => { context.beginPath(); context.arc(p.x, p.y, order === 0 ? 2.3 : 2, 0, Math.PI * 2); context.fill(); });
    });
  };

  const render = () => document.querySelectorAll(".reference-line-chart").forEach(draw);
  addEventListener("load", render, {once: true});
  addEventListener("resize", render, {passive: true});
})();
