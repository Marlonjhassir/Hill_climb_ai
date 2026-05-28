# Progreso del proyecto

## Fase actual: 8 — Generalización del entorno y demo visual 🔄 (en curso, 2026-05-28)

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
| `ai/genome.py` | ✅ | Genome con mutate(), copy(), forward() sin torch en la interfaz |
| `main.py` | ✅ | Modo `--mode random_ai` añadido; red controla el vehículo en tiempo real |

### PolicyNet — detalles
- Arquitectura construida dinámicamente desde `NN_INPUTS`, `NN_HIDDEN`, `NN_OUTPUTS` en `settings.py`.
- `requires_grad=False` en todos los parámetros al construir.
- `forward()` envuelto en `torch.no_grad()`.
- `get_weights()` → vector 1D NumPy float32, copia segura (`.detach().numpy().copy()`).
- `set_weights(weights)` → inyecta vector 1D con validación de tamaño.
- `n_params` → propiedad; para arquitectura 14→16→12→2 devuelve **470**.

---

---

## Fase 6 — Algoritmo Genético 🔄 (en curso, 2026-05-28)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `ai/genetic_algorithm.py` | ✅ | Torneo, crossover uniforme, elitismo |
| `ai/trainer.py` | ✅ | Orquestador headless: loop de generaciones, fitness, log |

### Detalles de GeneticAlgorithm
- `initialize()` — crea 50 `Genome` con pesos Kaiming aleatorios.
- `evolve()` — ordena por fitness, copia los 3 mejores (elitismo, fitness reset), completa con torneo + crossover + mutación.
- `_tournament_select()` — `random.sample` sin repetición, gana el de mayor fitness.
- `_crossover(a, b)` — `np.where(mask, w_a, w_b)` con mask 50%; activa con prob. `CROSSOVER_RATE=0.7`.

### Verificación de genetic_algorithm.py
- Población inicial de 50, todos con fitness=0.0 ✅
- `evolve()` produce exactamente 50 individuos con fitness reseteado ✅
- Pesos del mejor individuo preservados en los 3 élites ✅
- Crossover: cuando no se activa (prob. 30%), hijo = copia de parent_a ✅

### Verificación de trainer.py (5 generaciones, 50 individuos)
- Fitness promedio: 156 → 728 → 1505 → 2810 → 4192 (crecimiento sostenido) ✅
- Mejor fitness: monotónicamente no-decreciente en todas las generaciones ✅
- Peor fitness Gen 4 = 130 (en generaciones previas era 0): la población mejora ✅
- Gráfica de evolución guardada en `experiments/evolution_curve.png` ✅

---

---

## Fase 6 — Algoritmo Genético ✅ (completada 2026-05-28)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `ai/genetic_algorithm.py` | ✅ | Torneo, crossover uniforme, elitismo |
| `ai/trainer.py` | ✅ | Orquestador headless: loop de generaciones, fitness, log |

### Detalles de GeneticAlgorithm
- `initialize()` — crea 50 `Genome` con pesos Kaiming aleatorios.
- `evolve()` — ordena por fitness, copia los 3 mejores (elitismo, fitness reset), completa con torneo + crossover + mutación.
- `_tournament_select()` — `random.sample` sin repetición, gana el de mayor fitness.
- `_crossover(a, b)` — `np.where(mask, w_a, w_b)` con mask 50%; activa con prob. `CROSSOVER_RATE=0.7`.

### Verificación de genetic_algorithm.py
- Población inicial de 50, todos con fitness=0.0 ✅
- `evolve()` produce exactamente 50 individuos con fitness reseteado ✅
- Pesos del mejor individuo preservados en los 3 élites ✅
- Crossover: cuando no se activa (prob. 30%), hijo = copia de parent_a ✅

### Verificación de trainer.py (5 generaciones, 50 individuos)
- Fitness promedio: 156 → 728 → 1505 → 2810 → 4192 (crecimiento sostenido) ✅
- Mejor fitness: monotónicamente no-decreciente en todas las generaciones ✅
- Peor fitness Gen 4 = 130 (en generaciones previas era 0): la población mejora ✅
- Gráfica de evolución guardada en `experiments/evolution_curve.png` ✅

---

## Fase 7 — Persistencia 🔄 (en curso, 2026-05-28)

### Archivos modificados
| Archivo | Estado | Notas |
|---|---|---|
| `ai/trainer.py` | ✅ (1/2) | Persistencia implementada — falta modo watch en main.py |

### Persistencia en trainer.py — detalles
- `_ensure_dirs()` — crea `data/saved_models/` y `data/statistics/` si no existen.
- `_save_checkpoint(gen, population)` — escritura atómica (.tmp → os.replace) de:
  - `population_gen_N.pkl`: list[dict] con `{'weights': np.ndarray, 'fitness': float}` por individuo.
  - `best_genome.pt`: dict con tensor de pesos, fitness y número de generación.
- `_load_checkpoint()` — carga el pkl de mayor N; reconstruye Genome con `Genome() + set_weights()`; captura toda excepción y arranca limpio si hay corrupción.
- `_latest_checkpoint_gen()` — escanea MODEL_DIR con `glob("population_gen_*.pkl")`.
- `_save_stats_row(stats)` — append a `stats.csv` cada generación; cabecera solo si archivo nuevo.
- `train()` modificado: reanuda desde checkpoint si existe; usa `range(start_gen, start_gen + n_generations)`.

### Verificación de persistencia (7 gens + reanudación 3 gens)
- Segunda sesión arranca en gen 5 (cargado population_gen_4.pkl) ✅
- Pesos restaurados idénticos tras ciclo guardar/cargar ✅
- stats.csv tiene 10 filas de datos + 1 cabecera (7+3 gens) ✅
- CSV acumula correctamente entre sesiones ✅

### Modo watch — detalles
- `_load_best_genome()` en `main.py`: carga `best_genome.pt`, reconstruye `Genome` con `set_weights()`, devuelve (genome, fitness, generation).
- `env.generation` y `env.best_fitness` expuestos como atributos públicos en `environment.py`; `render()` los pasa a `ui.draw()`.
- HUD muestra GENERACION y MEJOR FIT correctamente en todos los modos.
- Título de ventana: `"Hill Climb AI — watch | gen N | fitness XXXX"`.

### Verificación completa de Fase 7
- Checkpoint guardado y cargado correctamente (7 gens + reanudación en gen 5) ✅
- Pesos restaurados idénticos tras ciclo guardar/cargar ✅
- CSV acumula filas entre sesiones ✅
- Modo watch carga el mejor genoma y lo muestra jugando ✅
- HUD muestra GENERACION: 5 y MEJOR FIT: 6503 en modo watch ✅

---

---

## Fase 8 — Generalización del entorno y demo visual 🔄 (en curso, 2026-05-28)

### Sub-fases

| Sub-fase | Descripción | Estado |
|---|---|---|
| 8.0 | Actualización del plan maestro (.tex) | ✅ |
| 8.1 | Terreno procedural (terrain.py) | ✅ |
| 8.2 | Obstáculos horneados (terrain.py) | ⬜ |
| 8.3 | Reset de checkpoint + espaciado progresivo | ⬜ |
| 8.4 | Modo demo (--mode demo en main.py) | ⬜ |

### Sub-fase 8.0 — Actualización del .tex ✅

Secciones actualizadas en `docs/plan_hill_climb_ai.tex`:
- Sección 4.1 (main.py): añadido `--mode demo`.
- Sección 4.2 (settings.py): añadido bloque de constantes Fase 8 con `TERRAIN_SEED_DEFAULT = 42`.
- Sección 4.3 (environment.py): documentado espaciado progresivo (sub-fase 8.3).
- Sección 4.4 (terrain.py): documentado diseño procedural con suma de sinusoides.
- Sección 4.8 (checkpoint.py): documentada decisión D2 (reset en lugar de acumulación).
- Sección 6.8 (FASE 8): reescrita con cuatro sub-fases y decisiones D1-D4.

### Sub-fase 8.1 — Terreno procedural ✅

#### Archivos modificados

| Archivo | Cambio |
|---|---|
| `config/settings.py` | Añadido `TERRAIN_SEED_DEFAULT = 42` |
| `game/terrain.py` | Reescritura completa: terreno procedural por suma de sinusoides |
| `game/environment.py` | `_render_terrain()` ahora muestrea `height_at(x)` en el viewport |

#### Diseño de terrain.py

- **Técnica:** suma de 4 sinusoides con fases aleatorias seedeadas vía `np.random.default_rng(seed)`.
- **Ondas:** macro-A (T=2200, A=70), macro-B (T=1400, A=50), medium (T=700, A=25), micro (T=280, A=10).
- **Zona plana:** `x ∈ [0, 400]` devuelve siempre `y = 500`.
- **Dificultad creciente:** factor lineal de 1× (x=400) a 3× (x=3400), fijo más allá.
- **Dominio abierto:** `height_at(x)` válido para cualquier `x ≥ 0`.
- **Física:** segmentos pymunk muestreados cada 20 px hasta x=5000.
- **Render:** muestreo dinámico cada 10 px en el viewport visible (sin lista fija).
- **slope_at():** diferenciación numérica centrada con ε=1 px (error O(ε²) despreciable).

#### Notebook de verificación

`experiments/terrain_profile.ipynb` — 4 celdas:
1. Setup headless (SDL_VIDEODRIVER=dummy).
2. Muestreo de height_at() para x ∈ [0, 5000] con dos semillas.
3. Gráfica de perfiles (muestra zona plana, dificultad creciente, meseta máxima).
4. Verificación de determinismo (dos instancias con el mismo seed → diff=0).

#### Ajustes post-verificación

| Archivo | Cambio | Razón |
|---|---|---|
| `game/terrain.py` | `amp_factor` arranca en 0 (no en 1×) en x=400 | Transición suave desde zona plana; colina inicial demasiado abrupta |
| `game/terrain.py` | `_MAX_AMP_FACTOR` 3.0 → 2.0 | Cap de pendiente máxima teórica ≈ 60° (antes podía llegar a ~69°) |
| `game/vehicle.py` | `MOTOR_MAX_FORCE` 80 000 → 120 000 | Potencia suficiente para superar pendientes de hasta ~55° |

**Nota:** con terreno procedural los checkpoints anteriores son inválidos. Se reentrenará desde cero a partir de sub-fase 8.3.

---

## Último avance
- Fecha: 2026-05-28
- Archivos: `docs/plan_hill_climb_ai.tex`, `config/settings.py`, `game/terrain.py`, `game/environment.py`, `experiments/terrain_profile.ipynb`, `game/vehicle.py`
- Estado: sub-fases 8.0 y 8.1 completadas — terreno procedural + motor ajustado para pendientes crecientes

## Siguiente paso
- Sub-fase 8.2: obstáculos horneados en `game/terrain.py` (ondas de alta frecuencia que simulan rocas y rampas).
- Sub-fase 8.3: reset de checkpoint + espaciado progresivo de monedas y checkpoints.
- Sub-fase 8.4: modo demo (`--mode demo` en `main.py`).