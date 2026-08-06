(() => {
  'use strict';

  const FIXED_TILT = 0.52;
  const VEHICLE_DARK = '#0F3D3E';
  const VEHICLE_GREEN = '#1DAA8A';
  const VEHICLE_YELLOW = '#F5B400';
  const VEHICLE_RED = '#E63946';

  function face(target, points, fill, stroke = VEHICLE_DARK, width = 1.6) {
    polygon(target, points, fill, stroke, width);
  }

  function point(longitudinal, transverse, vertical, origin, scale) {
    return projectWorld(longitudinal, transverse, vertical, origin, scale, state);
  }

  function drawWheel(target, longitudinal, transverse, origin, scale) {
    const center = point(longitudinal, transverse, -190, origin, scale);
    target.save();
    target.translate(center[0], center[1]);
    target.rotate(state.angle * 0.18);
    target.beginPath();
    target.ellipse(0, 0, 17, 11, 0, 0, Math.PI * 2);
    target.fillStyle = '#17252B';
    target.fill();
    target.lineWidth = 2;
    target.strokeStyle = '#07161B';
    target.stroke();
    target.beginPath();
    target.ellipse(0, 0, 7, 4.5, 0, 0, Math.PI * 2);
    target.fillStyle = '#87959B';
    target.fill();
    target.restore();
  }

  function drawCab(target, vehicle, origin, scale) {
    const L = vehicle.interior_length_mm;
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;
    const cabLength = Math.min(1650, Math.max(1050, L * 0.11));
    const cabStart = L + 170;
    const cabWidth = W * 0.86;
    const cabOffset = (W - cabWidth) / 2;
    const cabHeight = H * 0.68;
    const bonnetLength = cabLength * 0.28;
    const points = cuboidPoints(cabStart, cabOffset, cabWidth, cabLength, -25, cabHeight, origin, scale, state);

    face(target, [points.A, points.B, points.F, points.E], '#137C77');
    face(target, [points.B, points.C, points.G, points.F], '#0C625F');
    face(target, [points.E, points.F, points.G, points.H], VEHICLE_GREEN);

    const windscreenStart = cabStart + bonnetLength;
    const windscreen = [
      point(windscreenStart, cabOffset + 40, cabHeight * 0.58, origin, scale),
      point(cabStart + cabLength - 70, cabOffset + 40, cabHeight * 0.58, origin, scale),
      point(cabStart + cabLength - 70, cabOffset + 40, cabHeight * 0.9, origin, scale),
      point(windscreenStart, cabOffset + 40, cabHeight * 0.9, origin, scale),
    ];
    face(target, windscreen, '#D8F3EA', VEHICLE_DARK, 1.2);

    const accentA = point(cabStart + 80, cabOffset + cabWidth, cabHeight * 0.2, origin, scale);
    const accentB = point(cabStart + bonnetLength, cabOffset + cabWidth, cabHeight * 0.2, origin, scale);
    line(target, accentA, accentB, VEHICLE_YELLOW, 5);
    const accentC = point(cabStart + cabLength * 0.68, cabOffset + cabWidth, cabHeight * 0.2, origin, scale);
    const accentD = point(cabStart + cabLength - 80, cabOffset + cabWidth, cabHeight * 0.2, origin, scale);
    line(target, accentC, accentD, VEHICLE_RED, 5);
  }

  function drawTrailerBody(target, vehicle, origin, scale) {
    const L = vehicle.interior_length_mm;
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;
    const underbody = -210;

    const chassis = [
      point(0, 0, underbody, origin, scale),
      point(L, 0, underbody, origin, scale),
      point(L, W, underbody, origin, scale),
      point(0, W, underbody, origin, scale),
    ];
    face(target, chassis, '#334A50', '#12262B', 2);

    const leftSkirt = [
      point(0, 0, underbody, origin, scale),
      point(L, 0, underbody, origin, scale),
      point(L, 0, 0, origin, scale),
      point(0, 0, 0, origin, scale),
    ];
    const rightSkirt = [
      point(0, W, underbody, origin, scale),
      point(L, W, underbody, origin, scale),
      point(L, W, 0, origin, scale),
      point(0, W, 0, origin, scale),
    ];
    face(target, leftSkirt, '#49646B', '#12262B', 1.7);
    face(target, rightSkirt, '#3D5960', '#12262B', 1.7);

    const frontBulkhead = [
      point(L, 0, 0, origin, scale),
      point(L, W, 0, origin, scale),
      point(L, W, H, origin, scale),
      point(L, 0, H, origin, scale),
    ];
    face(target, frontBulkhead, 'rgba(15,61,62,.13)', VEHICLE_DARK, 2.4);

    const roof = [
      point(0, 0, H, origin, scale),
      point(L, 0, H, origin, scale),
      point(L, W, H, origin, scale),
      point(0, W, H, origin, scale),
    ];
    face(target, roof, 'rgba(29,170,138,.055)', 'rgba(15,61,62,.55)', 1.5);

    const rearCorners = [
      [point(0, 0, 0, origin, scale), point(0, 0, H, origin, scale)],
      [point(0, W, 0, origin, scale), point(0, W, H, origin, scale)],
      [point(0, 0, H, origin, scale), point(0, W, H, origin, scale)],
      [point(0, 0, 0, origin, scale), point(0, W, 0, origin, scale)],
    ];
    rearCorners.forEach(([a, b]) => line(target, a, b, VEHICLE_DARK, 4));

    const thresholdA = point(-70, -70, -35, origin, scale);
    const thresholdB = point(-70, W + 70, -35, origin, scale);
    line(target, thresholdA, thresholdB, VEHICLE_YELLOW, 6);

    const wheelPositions = [L * 0.2, L * 0.76, L * 0.84];
    wheelPositions.forEach(position => {
      drawWheel(target, position, -155, origin, scale);
      drawWheel(target, position, W + 155, origin, scale);
    });

    drawCab(target, vehicle, origin, scale);
  }

  function installOpaqueCargo() {
    if (typeof hexToRgba !== 'function' || hexToRgba.__logipilotOpaqueCargo) return;
    const original = hexToRgba;
    const opaque = function logipilotOpaqueCargo(hex, alpha) {
      return original(hex, Number(alpha) >= 0.4 ? 1 : alpha);
    };
    opaque.__logipilotOpaqueCargo = true;
    hexToRgba = opaque;
  }

  function installVehicleRendering() {
    if (typeof drawScene !== 'function' || drawScene.__logipilotVehicle) return;
    const original = drawScene;
    const enhanced = function logipilotVehicleScene(target, targetCanvas, options = {}) {
      state.tilt = FIXED_TILT;
      original(target, targetCanvas, options);
      if (!state.result?.solutions?.length) return;
      const solution = state.result.solutions[state.selected];
      const plan = solution?.vehicle_plans?.[state.selectedVehicle];
      if (!plan) return;
      const vehicle = vehicleFor(plan);
      const max = Math.max(vehicle.interior_length_mm, vehicle.interior_width_mm, vehicle.interior_height_mm * 1.7);
      const scale = (targetCanvas.width / 1000) * 430 / max * state.zoom;
      const origin = [targetCanvas.width * 0.44, targetCanvas.height * 0.76];
      drawTrailerBody(target, vehicle, origin, scale);
    };
    enhanced.__logipilotVehicle = true;
    drawScene = enhanced;
  }

  function installFixedPerspective() {
    if (typeof canvas === 'undefined' || !canvas || canvas.dataset.fixedPerspective === '1') return;
    canvas.dataset.fixedPerspective = '1';
    state.tilt = FIXED_TILT;

    canvas.addEventListener('pointermove', event => {
      if (!state.drag || state.drag.mode !== 'orbit') return;
      const dx = event.clientX - state.drag.x;
      const dy = event.clientY - state.drag.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) state.drag.moved = true;
      state.angle = state.drag.angle + dx * 0.008;
      state.tilt = FIXED_TILT;
      drawViewer();
      event.preventDefault();
      event.stopImmediatePropagation();
    }, { capture: true });

    const help = document.querySelector('.viewer-help');
    if (help) help.textContent = 'Glisser horizontalement pour tourner · Maj + glisser pour déplacer la caméra · molette pour zoomer · cliquer sur un objet pour l’inspecter';
  }

  function init() {
    installOpaqueCargo();
    installVehicleRendering();
    installFixedPerspective();
    if (typeof drawViewer === 'function') drawViewer();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
