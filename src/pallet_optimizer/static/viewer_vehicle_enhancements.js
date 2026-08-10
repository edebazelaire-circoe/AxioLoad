(() => {
  'use strict';

  const FIXED_TILT = 0.52;
  const DEFAULT_ZOOM = 1.45;
  const VEHICLE_DARK = '#0F3D3E';
  const VEHICLE_GREEN = '#1DAA8A';
  const VEHICLE_GREEN_DARK = '#137C77';
  const VEHICLE_YELLOW = '#F5B400';
  const VEHICLE_RED = '#E63946';
  const DIMENSION_BLUE = '#00A8BF';
  const FLOOR = '#DCE9E8';
  const FLOOR_EDGE = '#45676A';
  const CHASSIS = '#324B50';

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

  function focusLength(vehicle) {
    return Number(vehicle.interior_length_mm || 0);
  }

  function sceneLayout(targetCanvas, vehicle, displayedLength) {
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;
    const underbody = -180;
    const corners = [
      [0, 0, underbody], [displayedLength, 0, underbody],
      [displayedLength, W, underbody], [0, W, underbody],
      [0, 0, H], [displayedLength, 0, H],
      [displayedLength, W, H], [0, W, H],
    ].map(values => rawProjection(...values));
    const xs = corners.map(value => value[0]);
    const ys = corners.map(value => value[1]);
    const width = Math.max(...xs) - Math.min(...xs) || 1;
    const height = Math.max(...ys) - Math.min(...ys) || 1;
    const zoomFactor = Math.max(0.55, Math.min(2.75, Number(state.zoom || DEFAULT_ZOOM) / DEFAULT_ZOOM));
    const scale = Math.min(
      targetCanvas.width * 0.72 / width,
      targetCanvas.height * 0.60 / height,
    ) * zoomFactor;
    const centreX = (Math.min(...xs) + Math.max(...xs)) / 2;
    const centreY = (Math.min(...ys) + Math.max(...ys)) / 2;
    return {
      scale,
      origin: [
        targetCanvas.width * 0.50 - centreX * scale,
        targetCanvas.height * 0.61 - centreY * scale,
      ],
    };
  }

  function drawFocusGrid(target, vehicle, displayedLength, origin, scale, scene) {
    const step = 1000;
    for (let longitudinal = step; longitudinal < displayedLength; longitudinal += step) {
      line(
        target,
        point(longitudinal, 0, 2, origin, scale),
        point(longitudinal, vehicle.interior_width_mm, 2, origin, scale),
        scene.grid,
        1,
        [6, 6],
      );
    }
    for (let transverse = step; transverse < vehicle.interior_width_mm; transverse += step) {
      line(
        target,
        point(0, transverse, 2, origin, scale),
        point(displayedLength, transverse, 2, origin, scale),
        scene.grid,
        1,
        [6, 6],
      );
    }
  }

  function drawWheel(target, longitudinal, transverse, origin, scale, size = 1) {
    const center = point(longitudinal, transverse, -205, origin, scale);
    target.save();
    target.translate(center[0], center[1]);
    target.rotate(state.angle * 0.12);
    target.beginPath();
    target.ellipse(0, 0, 14 * size, 9 * size, 0, 0, Math.PI * 2);
    target.fillStyle = '#18282D';
    target.fill();
    target.lineWidth = 1.8;
    target.strokeStyle = '#07161B';
    target.stroke();
    target.beginPath();
    target.ellipse(0, 0, 5.5 * size, 3.8 * size, 0, 0, Math.PI * 2);
    target.fillStyle = '#93A1A6';
    target.fill();
    target.restore();
  }

  function drawCutawayTrailer(target, vehicle, displayedLength, origin, scale, scene) {
    const W = vehicle.interior_width_mm;
    const H = vehicle.interior_height_mm;
    const underbody = -180;
    const lowRail = Math.min(230, H * 0.11);

    const floor = [
      point(0, 0, 0, origin, scale),
      point(displayedLength, 0, 0, origin, scale),
      point(displayedLength, W, 0, origin, scale),
      point(0, W, 0, origin, scale),
    ];
    face(target, floor, FLOOR, FLOOR_EDGE, 2.1);
    drawFocusGrid(target, vehicle, displayedLength, origin, scale, scene);

    const chassis = [
      point(0, 0, underbody, origin, scale),
      point(displayedLength, 0, underbody, origin, scale),
      point(displayedLength, W, underbody, origin, scale),
      point(0, W, underbody, origin, scale),
    ];
    face(target, chassis, CHASSIS, '#172D31', 1.8);

    const leftLowerPanel = [
      point(0, 0, underbody, origin, scale),
      point(displayedLength, 0, underbody, origin, scale),
      point(displayedLength, 0, lowRail, origin, scale),
      point(0, 0, lowRail, origin, scale),
    ];
    const rightLowerPanel = [
      point(0, W, underbody, origin, scale),
      point(displayedLength, W, underbody, origin, scale),
      point(displayedLength, W, lowRail, origin, scale),
      point(0, W, lowRail, origin, scale),
    ];
    face(target, leftLowerPanel, '#456268', '#172D31', 1.7);
    face(target, rightLowerPanel, '#3A575D', '#172D31', 1.7);

    const rearFrame = [
      [point(0, 0, 0, origin, scale), point(0, 0, H, origin, scale)],
      [point(0, W, 0, origin, scale), point(0, W, H, origin, scale)],
      [point(0, 0, H, origin, scale), point(0, W, H, origin, scale)],
      [point(0, 0, 0, origin, scale), point(0, W, 0, origin, scale)],
    ];
    rearFrame.forEach(([a, b]) => line(target, a, b, VEHICLE_DARK, 4));

    const topRails = [
      [point(0, 0, H, origin, scale), point(displayedLength, 0, H, origin, scale)],
      [point(0, W, H, origin, scale), point(displayedLength, W, H, origin, scale)],
    ];
    topRails.forEach(([a, b]) => line(target, a, b, 'rgba(15,61,62,.34)', 1.3, [7, 6]));

    const frontPanel = [
      point(displayedLength, 0, 0, origin, scale),
      point(displayedLength, W, 0, origin, scale),
      point(displayedLength, W, H, origin, scale),
      point(displayedLength, 0, H, origin, scale),
    ];
    face(target, frontPanel, 'rgba(29,170,138,.06)', 'rgba(15,61,62,.52)', 1.6);

    const thresholdA = point(-55, -55, -28, origin, scale);
    const thresholdB = point(-55, W + 55, -28, origin, scale);
    line(target, thresholdA, thresholdB, VEHICLE_YELLOW, 5);

    const axle = Math.max(displayedLength * 0.67, displayedLength - 1150);
    [axle - 260, axle + 260].forEach(position => {
      if (position <= 200 || position >= displayedLength - 100) return;
      drawWheel(target, position, -120, origin, scale, 0.9);
      drawWheel(target, position, W + 120, origin, scale, 0.9);
    });
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
    const width = exportMode ? 430 : Math.min(360, targetCanvas.width * 0.34);
    const height = exportMode ? 126 : 104;
    const x = 22;
    const y = 20;
    const occupied = occupiedLength(plan);
    const total = Number(vehicle.interior_length_mm || 0);
    const remaining = Math.max(0, total - occupied);
    const ratio = total > 0 ? Math.max(0, Math.min(1, occupied / total)) : 0;
    roundedRect(target, x, y, width, height, 12, 'rgba(255,255,255,.97)', 'rgba(15,61,62,.18)');

    target.save();
    target.fillStyle = VEHICLE_DARK;
    target.font = `800 ${exportMode ? 18 : 13}px Segoe UI, Arial, sans-serif`;
    target.fillText('Occupation de la longueur', x + 14, y + 22);

    const barX = x + 14;
    const barY = y + 38;
    const barW = width - 28;
    const barH = exportMode ? 16 : 12;
    roundedRect(target, barX, barY, barW, barH, barH / 2, '#E7EEF1', null);
    if (ratio > 0) {
      roundedRect(target, barX, barY, Math.max(4, barW * ratio), barH, barH / 2, VEHICLE_GREEN, null);
    }

    target.font = `700 ${exportMode ? 14 : 10.5}px Segoe UI, Arial, sans-serif`;
    target.fillStyle = VEHICLE_GREEN_DARK;
    target.fillText(`${fmt(occupied / 1000)} m occupés`, barX, y + height - 14);
    target.textAlign = 'center';
    target.fillStyle = '#526A70';
    target.fillText(`${fmt(remaining / 1000)} m restants`, x + width / 2, y + height - 14);
    target.textAlign = 'right';
    target.fillText(`${fmt(total / 1000)} m total`, x + width - 14, y + height - 14);
    target.restore();
  }

  function drawLoadingAnnotations(target, vehicle, plan, origin, scale, scene) {
    const total = Number(vehicle.interior_length_mm || 0);
    const occupied = Math.min(total, occupiedLength(plan));
    const free = Math.max(0, total - occupied);

    if (occupied > 50) {
      drawDimension(
        target,
        [0, vehicle.interior_width_mm + 520, 0],
        [occupied, vehicle.interior_width_mm + 520, 0],
        `Longueur occupée ${fmt(occupied / 1000)} m`,
        DIMENSION_BLUE,
        origin,
        scale,
        state,
      );
    }

    if (free > 100) {
      const freeCentre = point(occupied + free * 0.5, vehicle.interior_width_mm * 0.52, vehicle.interior_height_mm * 0.55, origin, scale);
      screenLabel(target, `Espace libre\n${fmt(free / 1000)} m`, freeCentre[0], freeCentre[1], {
        font: '800 12px Segoe UI, Arial, sans-serif',
        background: 'rgba(255,255,255,.96)',
        color: '#0B639F',
        border: 'rgba(0,168,191,.42)',
      });
    }

    drawDimension(
      target,
      [0, vehicle.interior_width_mm + 340, 0],
      [total, vehicle.interior_width_mm + 340, 0],
      `Longueur totale ${fmt(total / 1000)} m`,
      DIMENSION_BLUE,
      origin,
      scale,
      state,
    );
    drawDimension(
      target,
      [-220, 0, 0],
      [-220, vehicle.interior_width_mm, 0],
      `Largeur ${fmt(vehicle.interior_width_mm / 1000)} m`,
      DIMENSION_BLUE,
      origin,
      scale,
      state,
    );
    drawDimension(
      target,
      [0, vehicle.interior_width_mm + 210, 0],
      [0, vehicle.interior_width_mm + 210, vehicle.interior_height_mm],
      `Hauteur ${fmt(vehicle.interior_height_mm / 1000)} m`,
      DIMENSION_BLUE,
      origin,
      scale,
      state,
    );
  }

  function drawCutawayScene(target, targetCanvas, { interactive = false, exportMode = false } = {}) {
    if (!state.result?.solutions?.length) return;
    state.tilt = FIXED_TILT;
    const solution = state.result.solutions[state.selected];
    const plan = solution.vehicle_plans[state.selectedVehicle];
    const vehicle = vehicleFor(plan);
    const scene = sceneColors();
    const displayedLength = focusLength(vehicle);
    const layout = sceneLayout(targetCanvas, vehicle, displayedLength);

    target.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
    target.fillStyle = '#FFFFFF';
    target.fillRect(0, 0, targetCanvas.width, targetCanvas.height);
    if (interactive) state.hitAreas = [];

    drawCutawayTrailer(target, vehicle, displayedLength, layout.origin, layout.scale, scene);

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

    drawLoadingAnnotations(target, vehicle, plan, layout.origin, layout.scale, scene);
    drawVehicleOverview(target, targetCanvas, vehicle, plan, exportMode);

    const metrics = planMetricsFromPlacements(plan);
    screenLabel(target, `${fmt(metrics.occupiedM)} m occupés · ${fmt(metrics.linearMeters)} m.l.`, targetCanvas.width - 22, 24, {
      align: 'right',
      font: exportMode ? '800 18px Segoe UI, Arial, sans-serif' : '800 13px Segoe UI, Arial, sans-serif',
      background: 'rgba(255,255,255,.96)',
      color: VEHICLE_DARK,
      border: 'rgba(15,61,62,.20)',
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
      help.textContent = 'Glisser horizontalement pour tourner · Molette pour zoomer · Cliquer sur un objet pour l’inspecter';
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