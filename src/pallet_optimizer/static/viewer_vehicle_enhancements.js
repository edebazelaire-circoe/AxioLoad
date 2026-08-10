(() => {
  'use strict';

  const FIXED_TILT = 0.52;
  const DEFAULT_ZOOM = 1.45;
  const VEHICLE_DARK = '#0F3D3E';
  const VEHICLE_GREEN = '#1DAA8A';
  const VEHICLE_GREEN_DARK = '#137C77';
  const VEHICLE_YELLOW = '#F5B400';
  const VEHICLE_RED = '#E63946';
  const FLOOR = '#EAF4F3';
  const FLOOR_EDGE = '#45676A';

  function face(target, points, fill, stroke = VEHICLE_DARK, width = 1.6) {
    polygon(target, points, fill, stroke, width);
  }

  function point(longitudinal, transverse, vertical, origin, scale) {
    return projectWorld(longitudinal, transverse, vertical, origin, scale, state);
  }

  function rawProjection(longitudinal, transverse, vertical) {
    const angle = state.angle;
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    const lx = longitudinal * c - transverse * s;
    const ly = longitudinal * s + transverse * c;
    return [lx, ly * 0.42 - vertical * FIXED_TILT];
  }

  function occupiedLength(plan) {
    return Math.max(0, ...(plan.placements || []).map(placement => (
      Number(placement.y_mm || 0) + Number(placement.envelope_length_mm || placement.actual_length_mm || 0)
    )));
  }

  function displayedVehicleLength(vehicle) {
    return Number(vehicle.interior_length_mm || 0);
  }

  function sceneLayout(targetCanvas, vehicle, displayedLength) {
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;
    const corners = [
      [0, 0, 0], [displayedLength, 0, 0],
      [displayedLength, W, 0], [0, W, 0],
      [0, 0, H], [displayedLength, 0, H],
      [displayedLength, W, H], [0, W, H],
    ].map(values => rawProjection(...values));
    const xs = corners.map(value => value[0]);
    const ys = corners.map(value => value[1]);
    const width = Math.max(...xs) - Math.min(...xs) || 1;
    const height = Math.max(...ys) - Math.min(...ys) || 1;
    const zoomFactor = Math.max(0.55, Math.min(2.75, Number(state.zoom || DEFAULT_ZOOM) / DEFAULT_ZOOM));
    const scale = Math.min(
      targetCanvas.width * 0.76 / width,
      targetCanvas.height * 0.62 / height,
    ) * zoomFactor;
    const centreX = (Math.min(...xs) + Math.max(...xs)) / 2;
    const centreY = (Math.min(...ys) + Math.max(...ys)) / 2;
    return {
      scale,
      origin: [
        targetCanvas.width * 0.5 - centreX * scale,
        targetCanvas.height * 0.6 - centreY * scale,
      ],
    };
  }

  function drawReferenceGrid(target, vehicle, displayedLength, origin, scale, scene) {
    const step = 1000;
    for (let longitudinal = step; longitudinal < displayedLength; longitudinal += step) {
      line(
        target,
        point(longitudinal, 0, 2, origin, scale),
        point(longitudinal, vehicle.interior_width_mm, 2, origin, scale),
        scene.grid,
        1,
        [5, 7],
      );
    }
  }

  function drawRectangularTrailer(target, vehicle, displayedLength, origin, scale, scene) {
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;

    const floor = [
      point(0, 0, 0, origin, scale),
      point(displayedLength, 0, 0, origin, scale),
      point(displayedLength, W, 0, origin, scale),
      point(0, W, 0, origin, scale),
    ];
    face(target, floor, FLOOR, FLOOR_EDGE, 2.1);
    drawReferenceGrid(target, vehicle, displayedLength, origin, scale, scene);

    const leftWall = [
      point(0, 0, 0, origin, scale),
      point(displayedLength, 0, 0, origin, scale),
      point(displayedLength, 0, H, origin, scale),
      point(0, 0, H, origin, scale),
    ];
    face(target, leftWall, 'rgba(29,170,138,.045)', 'rgba(15,61,62,.42)', 1.4);

    const rightWall = [
      point(0, W, 0, origin, scale),
      point(displayedLength, W, 0, origin, scale),
      point(displayedLength, W, H, origin, scale),
      point(0, W, H, origin, scale),
    ];
    face(target, rightWall, 'rgba(29,170,138,.025)', 'rgba(15,61,62,.30)', 1.2);

    const frontPanel = [
      point(displayedLength, 0, 0, origin, scale),
      point(displayedLength, W, 0, origin, scale),
      point(displayedLength, W, H, origin, scale),
      point(displayedLength, 0, H, origin, scale),
    ];
    face(target, frontPanel, 'rgba(29,170,138,.09)', 'rgba(15,61,62,.58)', 1.6);

    const topRails = [
      [point(0, 0, H, origin, scale), point(displayedLength, 0, H, origin, scale)],
      [point(0, W, H, origin, scale), point(displayedLength, W, H, origin, scale)],
    ];
    topRails.forEach(([a, b]) => line(target, a, b, 'rgba(15,61,62,.28)', 1.1, [7, 7]));

    const thresholdA = point(-55, -55, -18, origin, scale);
    const thresholdB = point(-55, W + 55, -18, origin, scale);
    line(target, thresholdA, thresholdB, VEHICLE_YELLOW, 5);
  }

  function roundedRect(target, x, y, width, height, radius, fill, stroke) {
    target.save();
    target.beginPath();
    target.roundRect(x, y, width, height, radius);
    target.fillStyle = fill;
    target.fill();
    if (stroke) {
      target.strokeStyle = stroke;
      target.lineWidth = 1.3;
      target.stroke();
    }
    target.restore();
  }

  function drawVehicleOverview(target, targetCanvas, vehicle, plan, exportMode) {
    const width = exportMode ? 390 : Math.min(330, targetCanvas.width * 0.29);
    const height = exportMode ? 108 : 92;
    const x = 24;
    const y = 22;
    const occupied = occupiedLength(plan);
    const ratio = Math.max(0, Math.min(1, occupied / vehicle.interior_length_mm));
    roundedRect(target, x, y, width, height, 14, 'rgba(255,255,255,.96)', 'rgba(15,61,62,.22)');

    target.save();
    target.fillStyle = VEHICLE_DARK;
    target.font = `${exportMode ? 18 : 13}px Segoe UI, Arial, sans-serif`;
    target.fontWeight = '700';
    target.fillText('Occupation de la longueur', x + 16, y + 23);

    const trailerX = x + 16;
    const trailerY = y + 40;
    const trailerW = width - 72;
    const trailerH = exportMode ? 34 : 28;
    roundedRect(target, trailerX, trailerY, trailerW, trailerH, 6, '#F4F8F8', VEHICLE_DARK);
    target.fillStyle = VEHICLE_GREEN;
    target.fillRect(trailerX + 2, trailerY + 2, Math.max(3, (trailerW - 4) * ratio), trailerH - 4);
    target.fillStyle = VEHICLE_YELLOW;
    target.fillRect(trailerX - 2, trailerY + 1, 4, trailerH - 2);

    const cabX = trailerX + trailerW + 5;
    const cabY = trailerY + 4;
    target.fillStyle = VEHICLE_GREEN_DARK;
    target.strokeStyle = VEHICLE_DARK;
    target.lineWidth = 1.3;
    target.beginPath();
    target.moveTo(cabX, cabY + trailerH - 5);
    target.lineTo(cabX + 30, cabY + trailerH - 5);
    target.lineTo(cabX + 30, cabY + 8);
    target.lineTo(cabX + 17, cabY);
    target.lineTo(cabX, cabY);
    target.closePath();
    target.fill();
    target.stroke();

    target.fillStyle = '#49666B';
    target.font = `${exportMode ? 15 : 11}px Segoe UI, Arial, sans-serif`;
    target.fillText(
      `${fmt(occupied / 1000)} m occupés sur ${fmt(vehicle.interior_length_mm / 1000)} m`,
      x + 16,
      y + height - 10,
    );
    target.restore();
  }

  function drawCutawayScene(target, targetCanvas, { interactive = false, exportMode = false } = {}) {
    if (!state.result?.solutions?.length) return;
    state.tilt = FIXED_TILT;
    const solution = state.result.solutions[state.selected];
    const plan = solution.vehicle_plans[state.selectedVehicle];
    const vehicle = vehicleFor(plan);
    const scene = sceneColors();
    const displayedLength = displayedVehicleLength(vehicle);
    const occupied = Math.min(displayedLength, occupiedLength(plan));
    const remaining = Math.max(0, displayedLength - occupied);
    const layout = sceneLayout(targetCanvas, vehicle, displayedLength);

    target.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
    target.fillStyle = '#FFFFFF';
    target.fillRect(0, 0, targetCanvas.width, targetCanvas.height);
    if (interactive) state.hitAreas = [];

    drawRectangularTrailer(target, vehicle, displayedLength, layout.origin, layout.scale, scene);

    (vehicle.obstacles || [])
      .filter(obstacle => Number(obstacle.y_mm || 0) < displayedLength)
      .forEach(obstacle => drawCuboid(target, {
        x_mm: obstacle.x_mm,
        y_mm: obstacle.y_mm,
        z_mm: 0,
        envelope_width_mm: obstacle.width_mm,
        envelope_length_mm: Math.min(obstacle.length_mm, displayedLength - obstacle.y_mm),
        actual_height_mm: obstacle.height_mm,
        item_id: obstacle.id,
        destination: 'Obstacle',
        weight_kg: 0,
        delivery_order: 0,
      }, '#8B95A1', layout.origin, layout.scale, state, { label: false }));

    const sorted = [...(plan.placements || [])]
      .sort((left, right) => (left.y_mm + left.x_mm) - (right.y_mm + right.x_mm));
    sorted.forEach((placement, index) => drawObject(
      target,
      placement,
      paletteColor(index),
      layout.origin,
      layout.scale,
      state,
      interactive,
    ));

    drawDimension(
      target,
      [0, vehicle.interior_width_mm + 380, 0],
      [displayedLength, vehicle.interior_width_mm + 380, 0],
      `Longueur totale ${fmt(displayedLength / 1000)} m`,
      '#005696',
      layout.origin,
      layout.scale,
      state,
    );

    if (occupied > 0) {
      drawDimension(
        target,
        [0, vehicle.interior_width_mm + 250, 0],
        [occupied, vehicle.interior_width_mm + 250, 0],
        `Longueur occupée ${fmt(occupied / 1000)} m`,
        '#00A8BF',
        layout.origin,
        layout.scale,
        state,
      );
    }

    drawDimension(
      target,
      [-220, 0, 0],
      [-220, vehicle.interior_width_mm, 0],
      `Largeur ${fmt(vehicle.interior_width_mm / 1000)} m`,
      VEHICLE_GREEN,
      layout.origin,
      layout.scale,
      state,
    );
    drawDimension(
      target,
      [0, vehicle.interior_width_mm + 125, 0],
      [0, vehicle.interior_width_mm + 125, vehicle.interior_height_mm],
      `Hauteur ${fmt(vehicle.interior_height_mm / 1000)} m`,
      VEHICLE_RED,
      layout.origin,
      layout.scale,
      state,
    );

    if (remaining > 100) {
      const freeLabel = point(occupied + remaining * 0.5, vehicle.interior_width_mm * 0.52, vehicle.interior_height_mm * 0.45, layout.origin, layout.scale);
      screenLabel(target, `Espace libre ${fmt(remaining / 1000)} m`, freeLabel[0], freeLabel[1], {
        font: '700 11px Segoe UI, Arial, sans-serif',
        background: 'rgba(255,255,255,.94)',
        color: VEHICLE_DARK,
        border: 'rgba(15,61,62,.30)',
      });
    }

    const rear = point(0, vehicle.interior_width_mm * 0.5, -20, layout.origin, layout.scale);
    screenLabel(target, 'Porte arrière', rear[0], rear[1] + 24, {
      font: '700 12px Segoe UI, Arial, sans-serif',
      background: scene.labelBackground,
      color: scene.labelColor,
      border: scene.labelBorder,
    });

    drawVehicleOverview(target, targetCanvas, vehicle, plan, exportMode);

    const metrics = planMetricsFromPlacements(plan);
    screenLabel(target, `${fmt(metrics.occupiedM)} m occupés · ${fmt(metrics.linearMeters)} m.l.`, targetCanvas.width - 22, 24, {
      align: 'right',
      font: exportMode ? '800 18px Segoe UI, Arial, sans-serif' : '800 13px Segoe UI, Arial, sans-serif',
      background: scene.metricBackground,
      color: '#FFFFFF',
      border: VEHICLE_DARK,
    });
  }

  function installOpaqueCargo() {
    if (typeof hexToRgba !== 'function' || hexToRgba.__logipilotOpaqueCargo) return;
    const original = hexToRgba;
    const opaque = function logipilotOpaqueCargo(hex, alpha) {
      return original(hex, Number(alpha) >= 0.2 ? 1 : alpha);
    };
    opaque.__logipilotOpaqueCargo = true;
    hexToRgba = opaque;
  }

  function installVehicleRendering() {
    if (typeof drawScene !== 'function' || drawScene.__logipilotCutawayVehicle) return;
    drawCutawayScene.__logipilotCutawayVehicle = true;
    drawScene = drawCutawayScene;
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
    if (help) {
      help.textContent = 'Glisser horizontalement pour tourner · Maj + glisser pour déplacer la caméra · molette pour zoomer · cliquer sur un objet pour l’inspecter';
    }
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