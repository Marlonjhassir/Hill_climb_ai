# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-27
- Archivo: `game/ui.py`
- Estado: completado y verificado
- Notas: panel semitransparente (SRCALPHA) creado una vez en __init__;
  5 filas con etiqueta + valor alineados; barra de tiempo con 3 colores
  (verde >50%, amarillo 20-50%, rojo <20%); verificación visual diferida
  hasta tener environment.py + main.py

## Siguiente paso
- Implementar `game/environment.py` (orquestador de todos los módulos)