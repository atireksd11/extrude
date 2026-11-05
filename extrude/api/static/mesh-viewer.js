/* Local canvas viewer: sampled geometry only, no external assets or scripts. */
window.ExtrudeMesh = {
  mount(container, mesh) {
    container.replaceChildren();
    const canvas = document.createElement("canvas");
    canvas.className = "artifact-canvas";
    canvas.setAttribute("aria-label", "3D geometry preview. Drag to rotate; scroll to zoom.");
    const caption = document.createElement("p");
    caption.className = "artifact-caption";
    caption.textContent = `Drag to rotate · Scroll to zoom · ${mesh.preview_sampled === false ? "Coarse display mesh; measurements use BREP geometry" : "Preview geometry may be sampled"}`;
    container.append(canvas, caption);
    const view = { yaw: -.55, pitch: -.36, zoom: 1, dragging: false, x: 0, y: 0 };
    const center = mesh.bounds.map(([a, b]) => (a + b) / 2);
    const span = Math.max(...mesh.dimensions, .001);
    let frame = null;
    function requestDraw() {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => { frame = null; draw(); });
    }
    function draw() {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(100, rect.width), height = 280, dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = width * dpr; canvas.height = height * dpr;
      const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
      const scale = Math.min(width, height) / (span * 1.5) * view.zoom;
      function project(p) {
        const [x, y, z] = p.map((n, i) => n - center[i]);
        const rx = x * cy + z * sy, rz = -x * sy + z * cy;
        return [width / 2 + rx * scale, height / 2 - (y * cp - rz * sp) * scale, y * sp + rz * cp];
      }
      const faces = mesh.triangles.map(t => {
        const p = [project(t.slice(0, 3)), project(t.slice(3, 6)), project(t.slice(6, 9))];
        return { p, z: p.reduce((sum, a) => sum + a[2], 0) / 3 };
      }).sort((a, b) => a.z - b.z);
      for (const { p } of faces) {
        ctx.beginPath(); ctx.moveTo(p[0][0], p[0][1]); ctx.lineTo(p[1][0], p[1][1]); ctx.lineTo(p[2][0], p[2][1]); ctx.closePath();
        const brightness = 48 + 16 * Math.min(1, Math.abs((p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0])) / (span * scale * span * scale));
        ctx.fillStyle = `hsl(173 39% ${brightness}%)`; ctx.fill();
        ctx.strokeStyle = "rgba(17,73,66,.27)"; ctx.lineWidth = .45; ctx.stroke();
      }
    }
    canvas.addEventListener("pointerdown", e => { view.dragging = true; view.x = e.clientX; view.y = e.clientY; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", e => { if (!view.dragging) return; view.yaw += (e.clientX - view.x) * .012; view.pitch = Math.max(-1.45, Math.min(1.45, view.pitch + (e.clientY - view.y) * .012)); view.x = e.clientX; view.y = e.clientY; requestDraw(); });
    for (const name of ["pointerup", "pointercancel"]) canvas.addEventListener(name, () => { view.dragging = false; });
    canvas.addEventListener("wheel", e => { e.preventDefault(); view.zoom = Math.max(.4, Math.min(3, view.zoom * (e.deltaY > 0 ? .9 : 1.1))); requestDraw(); }, { passive: false });
    const observer = new ResizeObserver(requestDraw); observer.observe(canvas); draw();
    return () => { observer.disconnect(); if (frame !== null) cancelAnimationFrame(frame); };
  }
};
