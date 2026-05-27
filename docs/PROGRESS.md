# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-27
- Archivo: `game/camera.py`
- Estado: completado y verificado
- Notas: lerp con LERP_FACTOR=5.0 en X e Y; camera.(x,y) es la esquina
  superior-izquierda del mundo visible; world_to_screen y screen_to_world
  verificadas con inversa exacta; convergencia gradual confirmada (no salto)

## Siguiente paso
- Implementar `game/ui.py` (HUD: score, distancia, tiempo)