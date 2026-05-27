# Progreso del proyecto

## Fase actual: 5 — Red Neuronal 🔄 (en curso, 2026-05-27)

## Fase 1 — Preparación ✅ (completada por el usuario)

Estructura de carpetas, entorno virtual, dependencias instaladas, git inicializado.

---

## Fase 2 — Juego Manual ✅ (completada 2026-05-27)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `config/settings.py` | ✅ | Escrito por el usuario, verificado |
| `game/physics.py` | ✅ | pymunk 7.x: on_collision, VEHICLE_GROUP |
| `game/terrain.py` | ✅ | 21 puntos fijos, zona plana en spawn (x=0..300) |
| `game/vehicle.py` | ✅ | ShapeFilter, MOTOR_MAX_FORCE=50000, rate negado |
| `game/player.py` | ✅ | ShapeFilter(group=VEHICLE_GROUP) |
| `game/camera.py` | ✅ | Lerp frame-rate independent |
| `game/ui.py` | ✅ | Panel semitransparente + barra de tiempo |
| `game/environment.py` | ✅ | Orquestador; get_state() stub |
| `main.py` | ✅ | Game loop, D/→ acelera, A/← frena, reset tras 1 s |

### Bugs corregidos durante verificación
- **ShapeFilter faltante**: ruedas y chasis se solapaban 20.5px → VEHICLE_GROUP=1 a todas las shapes.
- **Pendiente en zona de spawn**: normal con componente horizontal empujaba el vehículo. FIX: zona plana x=0..300.
- **Dirección del motor invertida**: `rate = -ACCELERATION_RATE * net`.
- **Potencia insuficiente**: MOTOR_MAX_FORCE=8000 → 50000.

---

## Fase 3 — Sistema de Recompensas ✅ (completada 2026-05-27)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `game/coin.py` | ✅ | Body STATIC, sensor=True, COLLISION_COIN=5 |
| `game/checkpoint.py` | ✅ | Segment vertical sensor=True, CHECKPOINT_WIDTH=8, CHECKPOINT_HEIGHT=200 |
| `ai/reward_system.py` | ✅ | compute_reward() pura: progreso + velocidad + muerte |
| `game/environment.py` | ✅ | Integración completa: coins, checkpoints, reward |

### Detalles de integración en environment.py
- `_coin_map: dict[shape→Coin]`: 19 monedas cada 200 px desde x=400 hasta x=4000.
- `_checkpoint_map: dict[shape→Checkpoint]`: 5 puertas en x=700, 1400, 2100, 2800, 3500.
- `step()`: pop(shape, None) para recolección segura (anti-duplicados).
- `_delta_distance`: calculado como max_distance - prev_max cada frame.
- `_compute_reward()`: delega a compute_reward(velocity_x, delta_distance, done).
- `render()`: capas coins y checkpoints entre terreno y vehículo, con culling.

### Resultado verificado
- Monedas doradas visibles en intervalos regulares ✅
- 5 postes verdes con bandera blanca ✅
- Score aumenta al recoger moneda ✅
- Tiempo aumenta al cruzar checkpoint ✅
- HUD refleja cambios en tiempo real ✅

---

## Fase 4 — Estados de IA ✅ (completada 2026-05-27)

### Archivos modificados
| Archivo | Estado | Notas |
|---|---|---|
| `game/physics.py` | ✅ | Contacto ruedas: pre_solve handler, register_wheel_shapes(), flags back/front_wheel_on_ground |
| `game/environment.py` | ✅ | get_state() completa: 14 entradas normalizadas + atan2 fix |
| `experiments/plots.ipynb` | ✅ | 5 celdas: setup headless, recolección, gráfica agrupada, estadísticas |

### get_state() — 14 entradas (índices 0-13)
| # | Variable | Normalización | Notas |
|---|---|---|---|
| 0 | vx | / 600 px/s | velocidad horizontal chasis |
| 1 | vy | / 600 px/s | velocidad vertical chasis |
| 2 | ángulo | atan2(sin, cos) / π | siempre en (-1, 1] — fix necesario por acumulación |
| 3 | omega | / 10 rad/s | velocidad angular |
| 4 | contacto trasero | 0.0 / 1.0 | flag via pre_solve en physics.py |
| 5 | contacto delantero | 0.0 / 1.0 | flag via pre_solve en physics.py |
| 6-9 | lookaheads +30/80/150/250 px | / 200 px | altura relativa al suelo actual |
| 10 | pendiente | / 0.5 | slope_at(chassis_x) |
| 11 | dx moneda | / 1280 px | horizontal a moneda más cercana |
| 12 | dy moneda | / 400 px | vertical a moneda más cercana |
| 13 | tiempo norm. | / MAX_TIME | clamp [0, 1] |

### Verificación (plots.ipynb, seed=42, siempre acelerar, 1200 frames)
- Distancia: 6331 px, Score: 19 monedas recogidas
- vx, omega, lookaheads, pendiente, dy: nunca saturan ✅
- ángulo: fix atan2 aplicado → min=-0.999, max=0.997, sat%=0.6% ✅
- rueda trasera/delantera: saturación ~50% es esperada (valores binarios 0/1) ✅
- tiempo norm.: saturación ~91% es esperada (vehicle cruza todos los checkpoints) ✅
- vy: 38% saturación → _VY_NORM podría subirse a 900; no crítico para Fase 5 ⚠️
- dx moneda: 43% saturación → _COIN_X_NORM podría subirse; no crítico para Fase 5 ⚠️

### Bug corregido
- **Ángulo no acotado:** `chassis.angle / math.pi` podía superar ±1 si el vehículo se
  inclinaba > 180°. Fix: `math.atan2(math.sin(chassis.angle), math.cos(chassis.angle)) / math.pi`.
  pymunk acumula el ángulo sin límite; atan2 recupera el canónico en (-π, π] siempre.

---

## Deuda técnica — Fase 8

### Comportamiento de checkpoints: acumular vs. resetear

**Problema:** el plan maestro describe `MAX_TIME` como "segundos *sin checkpoint* → muerte",
lo que implica un contador de inactividad que se *resetea* al cruzar un checkpoint.
La implementación actual lo trata como tiempo acumulable (`time_left += CHECKPOINT_TIME`).

**Impacto en terreno fijo (Fases 2-7):** ninguno observable. El tiempo máximo sigue siendo
acotado (20 + 5×10 = 70 s) y el comportamiento del juego es correcto.

**Impacto potencial en Fase 8 (terreno procedural):** si el mapa generado coloca checkpoints
en zonas densas, el vehículo podría cruzarlos todos rápido y luego tener tiempo libre
sin incentivo para avanzar. El enfoque reset-en-checkpoint forzaría al agente a llegar
al siguiente checkpoint antes de que el contador llegue a cero.

**Acción pendiente para Fase 8:** decidir si `time_left += CHECKPOINT_TIME` (acumulativo,
actual) o `time_left = MAX_TIME + CHECKPOINT_TIME` (reset, según el plan). Evaluar con
terreno procedural cuál produce mejor comportamiento de aprendizaje.

---

---

## Fase 5 — Red Neuronal 🔄 (en curso, 2026-05-27)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `ai/neural_network.py` | ✅ | PolicyNet 14→16(tanh)→12(tanh)→2(sigmoid), sin gradientes |
| `ai/genome.py` | ⬜ | Pendiente |

### PolicyNet — detalles
- Arquitectura construida dinámicamente desde `NN_INPUTS`, `NN_HIDDEN`, `NN_OUTPUTS` en `settings.py`.
- `requires_grad=False` en todos los parámetros al construir.
- `forward()` envuelto en `torch.no_grad()`.
- `get_weights()` → vector 1D NumPy float32, copia segura (`.detach().numpy().copy()`).
- `set_weights(weights)` → inyecta vector 1D con validación de tamaño.
- `n_params` → propiedad; para arquitectura 14→16→12→2 devuelve **470**.

---

## Último avance
- Fecha: 2026-05-27
- Archivo: `ai/neural_network.py`
- Estado: PolicyNet implementada y lista para verificación

## Siguiente paso
- `ai/genome.py`: clase Genome que encapsula PolicyNet + fitness + operadores evolutivos