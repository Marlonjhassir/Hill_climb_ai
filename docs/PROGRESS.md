# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-27
- Archivo: `game/vehicle.py`
- Estado: completado y verificado
- Notas: chasis (Poly.create_box, CHASSIS_MASS), dos ruedas (Circle, WHEEL_MASS),
  PivotJoint para suspensión rígida, SimpleMotor con tracción 100% trasera y 60%
  delantera; contactos como flags públicos que environment.py actualiza;
  spawn_y calculado como height_at(x) - WHEEL_OFFSET_Y - WHEEL_RADIUS

## Siguiente paso
- Implementar `game/player.py` (conductor + colisión con suelo)