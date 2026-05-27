"""
game/environment.py — Orquestador de todos los módulos del juego.

Responsabilidades:
  - Crear y conectar: PhysicsEngine, Terrain, Vehicle, Player, Camera, UI,
    Coin (mapa de monedas) y Checkpoint (mapa de puertas de tiempo).
  - En step(): aplicar acción → avanzar física → leer eventos → actualizar estado.
  - En render(): dibujar todos los elementos en orden de capas (back-to-front).
  - Exponer get_state() (stub hasta Fase 4) y step() con interfaz tipo Gym.

Prohibido: contener física directa (delegar a PhysicsEngine), dibujar sin
transformar por la cámara, leer inputs de teclado (eso va en main.py).
"""

import math

import pygame
import pymunk

from ai.reward_system import compute_reward
from config.settings import (
    CHECKPOINT_TIME, LOOKAHEAD_DISTANCES, MAX_TIME, SCREEN_HEIGHT, SCREEN_WIDTH,
)
from game.camera import Camera
from game.checkpoint import Checkpoint, CHECKPOINT_HEIGHT, CHECKPOINT_WIDTH
from game.coin import Coin, COIN_RADIUS, COIN_VALUE, COIN_Y_OFFSET
from game.physics import PhysicsEngine
from game.player import Player, PLAYER_HEIGHT, PLAYER_WIDTH
from game.terrain import Terrain
from game.ui import UI
from game.vehicle import (
    CHASSIS_HEIGHT, CHASSIS_WIDTH,
    WHEEL_OFFSET_Y, WHEEL_RADIUS,
    Vehicle,
)

# Posición horizontal de spawn del vehículo (coordenadas mundo)
SPAWN_X: float = 100.0

# Monedas: una cada _COIN_SPACING px, desde _COIN_START_X hasta x=4000
_COIN_SPACING: int = 200   # px entre monedas consecutivas
_COIN_START_X: int = 400   # primera moneda (deja margen libre en la zona de spawn)

# Posiciones X de los 5 checkpoints, distribuidos a lo largo del terreno (~4 km)
_CHECKPOINT_X_POSITIONS: tuple[int, ...] = (700, 1400, 2100, 2800, 3500)

# ---------------------------------------------------------------------------
# Constantes de normalización para get_state()
# ---------------------------------------------------------------------------
# La red neuronal trabaja bien cuando sus entradas están en [-1, 1].
# Para lograrlo dividimos cada valor por la magnitud máxima esperada.
# Estos máximos son empíricos: si la IA recibe valores > 1 de forma habitual,
# se pueden subir; si están siempre muy por debajo de 1, se pueden bajar.

_VX_NORM     = 600.0   # px/s — velocidad horizontal máxima esperada del chasis
_VY_NORM     = 600.0   # px/s — velocidad vertical máxima esperada del chasis
_OMEGA_NORM  = 10.0    # rad/s — velocidad angular máxima del chasis
_HEIGHT_NORM = 200.0   # px — diferencia de altura máxima en el lookahead
_SLOPE_NORM  = 0.5     # px/px — pendiente máxima del terreno (|ΔY/ΔX|)
_COIN_X_NORM = 1280.0  # px — distancia horizontal máxima hasta moneda (≈ SCREEN_WIDTH)
_COIN_Y_NORM = 400.0   # px — distancia vertical máxima hasta moneda

# ---------------------------------------------------------------------------
# Paleta de colores para renderizado placeholder (sin sprites aún)
# ---------------------------------------------------------------------------
_SKY_COLOR       = (100, 160, 230)   # azul cielo
_GROUND_FILL     = (85,  65,  45)    # marrón tierra
_GROUND_LINE     = (110, 85,  60)    # marrón claro para la superficie
_WHEEL_COL       = (40,  40,  40)    # gris oscuro rueda
_WHEEL_RIM       = (200, 200, 200)   # gris claro llanta
_CHASSIS_COL     = (180, 50,  50)    # rojo chasis
_CHASSIS_EDGE    = (230, 100, 100)   # rojo claro borde
_PLAYER_COL      = (50,  120, 220)   # azul conductor
_COIN_COLOR      = (255, 215,   0)   # dorado moneda
_COIN_OUTLINE    = (200, 150,   0)   # contorno dorado oscuro
_CHECKPOINT_COL  = (50,  200, 100)   # verde poste
_CHECKPOINT_FLAG = (255, 255, 255)   # blanco bandera


# ---------------------------------------------------------------------------
# Función auxiliar de geometría
# ---------------------------------------------------------------------------

def _rotated_box(
    cx: float, cy: float,
    w: float,  h: float,
    angle: float,
) -> list[tuple[float, float]]:
    """
    Calcula los 4 vértices de un rectángulo rotado centrado en (cx, cy).

    pygame no tiene draw.rect con rotación, así que calculamos los vértices
    a mano y usamos draw.polygon.

    La fórmula de rotación 2D para cada vértice (lx, ly) en coords locales:
        mundo_x = cx + lx * cos(angle) - ly * sin(angle)
        mundo_y = cy + lx * sin(angle) + ly * cos(angle)

    Args:
        cx, cy: centro del rectángulo en coords de pantalla (ya transformado).
        w, h:   ancho y alto en píxeles.
        angle:  ángulo en radianes (viene de pymunk body.angle).
    """
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    hw, hh = w / 2, h / 2
    # Cuatro esquinas en coordenadas locales (sin rotar)
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [
        (cx + lx * cos_a - ly * sin_a,
         cy + lx * sin_a + ly * cos_a)
        for lx, ly in corners
    ]


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class Environment:
    """
    Orquestador del juego: conecta física, renderizado y lógica de episodio.

    Interfaz mínima para main.py:
        env = Environment(seed=0)
        state, reward, done, info = env.step(action=(1.0, 0.0), dt=1/60)
        env.render(surface)
        env.reset()
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        # UI se crea de forma lazy en el primer render() para no requerir
        # pygame.display al construir el Environment (útil en modo headless).
        self._ui: UI | None = None
        self._reset_components()

    # ------------------------------------------------------------------
    # Ciclo de vida del episodio
    # ------------------------------------------------------------------

    def reset(self, seed: int | None = None) -> None:
        """
        Reinicia el episodio desde cero.

        Recrea todos los cuerpos físicos y resetea el estado del juego.
        El objeto Environment mismo no cambia: main.py puede llamar reset()
        en el mismo env en lugar de crear uno nuevo.

        Args:
            seed: nueva semilla de terreno. None conserva la semilla actual.
        """
        if seed is not None:
            self._seed = seed
        self._reset_components()

    def _reset_components(self) -> None:
        """Crea o recrea todos los componentes físicos y el estado del juego."""

        # PhysicsEngine primero: todos los demás necesitan su Space
        self._engine = PhysicsEngine()
        space = self._engine.get_space()

        # Terreno: su seed controla la forma del mapa para toda la generación
        self._terrain = Terrain(space=space, seed=self._seed)

        # Calcular spawn_y para que las ruedas queden justo sobre el suelo.
        # Fórmula: centro_chasis_y = altura_terreno - offset_rueda - radio_rueda
        self._spawn_x = SPAWN_X
        spawn_y = (
            self._terrain.height_at(SPAWN_X)
            - WHEEL_OFFSET_Y
            - WHEEL_RADIUS
        )

        self._vehicle = Vehicle(space=space, position=(SPAWN_X, spawn_y))
        self._player  = Player(space=space, chassis=self._vehicle.chassis)
        self._camera  = Camera()

        # Registrar las shapes de rueda en el engine para que el handler
        # wheel-terrain pueda distinguir cuál es la trasera y cuál la delantera.
        # Debe hacerse DESPUÉS de crear el vehículo (las shapes ya existen)
        # y ANTES del primer step() (el handler necesita las referencias).
        self._engine.register_wheel_shapes(
            self._vehicle.back_wheel_shape,
            self._vehicle.front_wheel_shape,
        )

        # Estado del episodio
        self.score: int            = 0
        self.max_distance: float   = 0.0   # distancia horizontal máxima desde spawn
        self.time_left: float      = MAX_TIME
        self.done: bool            = False
        # Cuántos px avanzó max_distance en el frame más reciente.
        # Se inicializa en 0; step() lo actualiza antes de llamar a _compute_reward().
        self._delta_distance: float = 0.0

        # Monedas: dict shape → Coin para búsqueda O(1) en los callbacks de colisión.
        # Cuando una moneda se recoge en step(), se elimina del dict Y del Space.
        # Así _coin_map.values() siempre representa solo las monedas activas.
        self._coin_map: dict[pymunk.Shape, Coin] = {}
        for x in range(_COIN_START_X, 4001, _COIN_SPACING):
            # La moneda flota COIN_Y_OFFSET px sobre el suelo.
            # height_at() devuelve la Y del suelo (Y crece hacia abajo), así que
            # restar COIN_Y_OFFSET mueve la moneda hacia arriba en pantalla.
            coin_y = self._terrain.height_at(float(x)) - COIN_Y_OFFSET
            coin = Coin(space, x=float(x), y=coin_y)
            self._coin_map[coin.shape] = coin

        # Checkpoints: mismo patrón dict shape → Checkpoint que las monedas.
        self._checkpoint_map: dict[pymunk.Shape, Checkpoint] = {}
        for x in _CHECKPOINT_X_POSITIONS:
            terrain_y = self._terrain.height_at(float(x))
            cp = Checkpoint(space, x=float(x), terrain_y=terrain_y)
            self._checkpoint_map[cp.shape] = cp

    # ------------------------------------------------------------------
    # Loop de simulación
    # ------------------------------------------------------------------

    def step(
        self,
        action: tuple[float, float],
        dt: float,
    ) -> tuple[list[float], float, bool, dict]:
        """
        Avanza la simulación un frame. Interfaz inspirada en OpenAI Gym.

        Orden de operaciones (importa hacerlo en este orden):
          1. Aplicar acción → vehicle.update()
          2. engine.step(dt) → pymunk mueve cuerpos y dispara collision handlers
          3. Leer eventos  → player_touched_ground, coins_collected, checkpoints_crossed
          4. Actualizar estado → tiempo, distancia, score
          5. Actualizar cámara → lerp hacia el chasis

        Args:
            action: (accel, brake) ambos en [0.0, 1.0].
            dt:     delta de tiempo en segundos (ej. 1/60).

        Returns:
            state   — vector de 14 entradas (stub [] hasta Fase 4).
            reward  — recompensa del frame.
            done    — True si el episodio terminó.
            info    — dict con métricas de debugging.
        """
        if self.done:
            return self.get_state(), 0.0, True, {}

        # Paso 1: aplicar acción al vehículo
        accel, brake = action
        self._vehicle.accelerate(accel)
        self._vehicle.brake(brake)
        self._vehicle.update(dt)

        # Paso 2: avanzar física (pymunk mueve bodies y dispara handlers)
        self._engine.step(dt)

        # Paso 3: leer eventos de colisión detectados por physics.py
        if self._engine.player_touched_ground:
            self.done = True

        # Propagar contactos de ruedas del engine al vehículo.
        # physics.py detecta el contacto vía pre_solve; vehicle.py expone los
        # flags para que get_state() los lea con la interfaz existente.
        self._vehicle.back_wheel_contact  = self._engine.back_wheel_on_ground
        self._vehicle.front_wheel_contact = self._engine.front_wheel_on_ground

        # Procesar monedas tocadas en este frame.
        # pop(shape, None) maneja de forma segura el caso de que la misma shape
        # aparezca dos veces (rueda + chasis activan el handler en el mismo step).
        space = self._engine.get_space()
        for shape in self._engine.coins_collected:
            coin = self._coin_map.pop(shape, None)
            if coin is not None:
                coin.remove_from_space(space)
                self.score += COIN_VALUE

        # Procesar checkpoints cruzados en este frame.
        # physics.py ya deduplicó la lista; pop(shape, None) protege igualmente.
        for shape in self._engine.checkpoints_crossed:
            cp = self._checkpoint_map.pop(shape, None)
            if cp is not None:
                # collect() elimina la shape del Space (la protección anti-doble
                # está en Checkpoint.collect, que además marca _active = False).
                cp.collect(space)
                # Añadir el bono ANTES de decrementar el tiempo garantiza que el
                # jugador vea el cambio en la misma iteración que cruzó la puerta.
                self.time_left += CHECKPOINT_TIME

        # Paso 4: actualizar estado del episodio

        # Tiempo restante: se decrementa cada frame
        self.time_left = max(0.0, self.time_left - dt)
        if self.time_left == 0.0:
            self.done = True

        # Distancia: solo contamos el avance hacia la derecha (máximo histórico).
        # Guardamos prev_max ANTES de actualizar para calcular el delta del frame.
        prev_max = self.max_distance
        current_dist = self._vehicle.chassis.position.x - self._spawn_x
        if current_dist > self.max_distance:
            self.max_distance = current_dist
        # _delta_distance = píxeles ganados en max_distance durante este frame.
        # Es 0 cuando el vehículo no supera su récord (parado, retrocediendo o
        # avanzando por terreno ya visitado).
        self._delta_distance = self.max_distance - prev_max

        # Paso 5: actualizar cámara para que siga al chasis
        chassis_pos = self._vehicle.chassis.position
        self._camera.update(chassis_pos.x, chassis_pos.y, dt)

        info = {
            'score':    self.score,
            'distance': self.max_distance,
            'time':     self.time_left,
            'coins':    len(self._coin_map),   # monedas que quedan por recoger
        }
        return self.get_state(), self._compute_reward(), self.done, info

    def _compute_reward(self) -> float:
        """
        Recompensa instantánea del frame actual, calculada por ai/reward_system.py.

        Esta función actúa como adaptador: extrae los valores del estado
        del juego y los pasa al módulo de recompensas, que aplica la lógica
        pura sin acceder al estado del Environment.
        """
        # velocity.x: positivo = avanzando a la derecha. Fuente: cuerpo del chasis.
        velocity_x = float(self._vehicle.chassis.velocity.x)
        return compute_reward(velocity_x, self._delta_distance, self.done)

    def get_state(self) -> list[float]:
        """
        Devuelve el vector de estado de 14 entradas para la red neuronal.

        Todos los valores están normalizados aproximadamente a [-1, 1] o [0, 1]
        para que ninguna entrada domine el cálculo de la red.

        Índices del vector:
            0  — vx normalizado (velocidad horizontal del chasis)
            1  — vy normalizado (velocidad vertical del chasis)
            2  — ángulo del chasis en [-1, 1] (radianes / π)
            3  — velocidad angular normalizada
            4  — contacto rueda trasera  (0.0 o 1.0)
            5  — contacto rueda delantera (0.0 o 1.0)
            6  — lookahead terreno a +30 px (relativo al suelo actual)
            7  — lookahead terreno a +80 px
            8  — lookahead terreno a +150 px
            9  — lookahead terreno a +250 px
            10 — pendiente del terreno en la posición actual
            11 — Δx a la moneda más cercana (normalizado)
            12 — Δy a la moneda más cercana (normalizado)
            13 — tiempo restante normalizado (0.0 a 1.0)
        """
        chassis  = self._vehicle.chassis
        vel      = chassis.velocity
        chassis_x = float(chassis.position.x)
        chassis_y = float(chassis.position.y)

        # Entradas 0-1: velocidades — clamp a [-1, 1] por si el vehículo
        # supera el máximo esperado en un momento puntual (ej. caída libre)
        vx = max(-1.0, min(1.0, vel.x / _VX_NORM))
        vy = max(-1.0, min(1.0, vel.y / _VY_NORM))

        # Entrada 2: ángulo — chassis.angle acumula rotaciones sin límite.
        # atan2(sin θ, cos θ) recupera el ángulo canónico en (-π, π] sin importar
        # cuántas vueltas haya dado el cuerpo. Dividir por π → siempre en (-1, 1].
        angle = math.atan2(math.sin(chassis.angle), math.cos(chassis.angle)) / math.pi

        # Entrada 3: velocidad angular — positivo = giro horario en pantalla
        omega = max(-1.0, min(1.0, chassis.angular_velocity / _OMEGA_NORM))

        # Entradas 4-5: contacto de ruedas — ya propagados en step()
        back_contact  = 1.0 if self._vehicle.back_wheel_contact  else 0.0
        front_contact = 1.0 if self._vehicle.front_wheel_contact else 0.0

        # Entradas 6-9: lookahead del terreno
        # Calculamos la diferencia de altura entre el suelo en la posición
        # del vehículo y el suelo a cada distancia hacia adelante.
        # Valor positivo → el suelo adelante está más abajo (bajada).
        # Valor negativo → el suelo adelante está más arriba (subida/colina).
        terrain_here = self._terrain.height_at(chassis_x)
        lookaheads: list[float] = []
        for offset in LOOKAHEAD_DISTANCES:
            raw = self._terrain.height_at(chassis_x + offset) - terrain_here
            lookaheads.append(max(-1.0, min(1.0, raw / _HEIGHT_NORM)))

        # Entrada 10: pendiente actual del terreno
        # slope_at() devuelve ΔY/ΔX. Con _SLOPE_NORM=0.5, una pendiente de
        # 0.5 (≈ 27°) mapea a 1.0. Pendientes mayores se clampean a ±1.
        slope = max(-1.0, min(1.0, self._terrain.slope_at(chassis_x) / _SLOPE_NORM))

        # Entradas 11-12: vector hasta la moneda más cercana
        if self._coin_map:
            # min() con key= evita crear una lista intermedia; O(n) sobre las monedas
            nearest = min(
                self._coin_map.values(),
                key=lambda c: (c.position.x - chassis_x) ** 2
                            + (c.position.y - chassis_y) ** 2,
            )
            dx = max(-1.0, min(1.0, (nearest.position.x - chassis_x) / _COIN_X_NORM))
            dy = max(-1.0, min(1.0, (nearest.position.y - chassis_y) / _COIN_Y_NORM))
        else:
            # Sin monedas restantes: indicar "no hay objetivo" con valores extremos.
            # La red aprenderá a ignorar estas entradas cuando ya no hay monedas.
            dx, dy = 1.0, 0.0

        # Entrada 13: tiempo restante — max_time puede crecer con checkpoints,
        # así que clamp a [0, 1] por si time_left supera MAX_TIME.
        time_norm = max(0.0, min(1.0, self.time_left / MAX_TIME))

        return [
            vx, vy, angle, omega,
            back_contact, front_contact,
            *lookaheads,
            slope,
            dx, dy,
            time_norm,
        ]

    # ------------------------------------------------------------------
    # Renderizado (back-to-front: lo primero dibujado queda detrás)
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        """
        Dibuja un frame completo sobre 'surface'.

        Orden de capas:
          1. Cielo (fondo completo)
          2. Terreno (detrás de todo)
          3. Monedas (encima del terreno, debajo del vehículo)
          4. Checkpoints (postes encima del terreno)
          5. Ruedas + chasis
          6. Conductor
          7. HUD (encima de todo, sin transformación de cámara)
        """
        if self._ui is None:
            self._ui = UI(surface)

        # Capa 1: fondo
        surface.fill(_SKY_COLOR)

        # Capas 2-6: mundo (usa camera.world_to_screen para posicionar)
        self._render_terrain(surface)
        self._render_coins(surface)
        self._render_checkpoints(surface)
        self._render_vehicle(surface)
        self._render_player(surface)

        # Capa 7: HUD (siempre en la misma posición de pantalla)
        self._ui.draw(
            score=self.score,
            distance=max(0.0, self.max_distance),
            time_left=self.time_left,
        )

    def _render_terrain(self, surface: pygame.Surface) -> None:
        """
        Dibuja el suelo: relleno sólido + línea de superficie.

        Convierte los puntos del terreno (mundo) a pantalla y construye:
          - Un polígono de relleno que va desde el primer punto, por toda
            la superficie, hasta el último, y cierra por el borde inferior.
          - Una línea más oscura sobre la superficie para distinguirla.
        """
        screen_pts = [
            (int(x), int(y))
            for x, y in (
                self._camera.world_to_screen(wx, wy)
                for wx, wy in self._terrain.points
            )
        ]

        if len(screen_pts) < 2:
            return

        # Polígono de relleno: cierra el suelo hasta el borde inferior
        fill_poly = (
            [(screen_pts[0][0], SCREEN_HEIGHT)]
            + screen_pts
            + [(screen_pts[-1][0], SCREEN_HEIGHT)]
        )
        pygame.draw.polygon(surface, _GROUND_FILL, fill_poly)

        # Línea de superficie encima del relleno
        for i in range(len(screen_pts) - 1):
            pygame.draw.line(
                surface, _GROUND_LINE,
                screen_pts[i], screen_pts[i + 1],
                4,
            )

    def _render_coins(self, surface: pygame.Surface) -> None:
        """
        Dibuja todas las monedas aún no recogidas.

        Itera sobre _coin_map, que solo contiene monedas activas (las recogidas
        se eliminan del dict en step()). El culling evita dibujar monedas que
        están fuera del área visible, ahorrando tiempo de CPU/GPU.
        """
        for coin in self._coin_map.values():
            sx, sy = self._camera.world_to_screen(*coin.position)
            cx, cy = int(sx), int(sy)
            # Culling: si el círculo completo queda fuera de pantalla, lo saltamos
            if (cx + COIN_RADIUS < 0 or cx - COIN_RADIUS > SCREEN_WIDTH or
                    cy + COIN_RADIUS < 0 or cy - COIN_RADIUS > SCREEN_HEIGHT):
                continue
            pygame.draw.circle(surface, _COIN_COLOR,   (cx, cy), COIN_RADIUS)
            pygame.draw.circle(surface, _COIN_OUTLINE, (cx, cy), COIN_RADIUS, 2)

    def _render_checkpoints(self, surface: pygame.Surface) -> None:
        """
        Dibuja todos los checkpoints aún no cruzados.

        Cada checkpoint se muestra como un poste verde vertical con una
        pequeña bandera blanca en la cima, al estilo de Hill Climb Racing.
        Los cruzados se han eliminado de _checkpoint_map en step(), así que
        no hace falta comprobar checkpoint.active aquí.
        """
        for cp in self._checkpoint_map.values():
            # Base del poste: nivel del suelo en la posición del checkpoint
            bx, by = self._camera.world_to_screen(cp.position_x, cp.terrain_y)
            # Cima del poste: CHECKPOINT_HEIGHT px por encima del suelo.
            # En nuestro sistema Y-abajo, restar altura sube en pantalla.
            tx, ty = self._camera.world_to_screen(
                cp.position_x,
                cp.terrain_y - CHECKPOINT_HEIGHT,
            )
            bx, by, tx, ty = int(bx), int(by), int(tx), int(ty)

            # Culling horizontal: el poste es vertical, su x es constante.
            # Omitimos si está completamente fuera del ancho de pantalla.
            if bx + CHECKPOINT_WIDTH < 0 or bx - CHECKPOINT_WIDTH > SCREEN_WIDTH:
                continue

            # Poste vertical: grosor = CHECKPOINT_WIDTH * 2 para que coincida
            # visualmente con la zona de colisión del Segment (radio=CHECKPOINT_WIDTH).
            pygame.draw.line(
                surface, _CHECKPOINT_COL,
                (tx, ty), (bx, by),
                CHECKPOINT_WIDTH * 2,
            )

            # Bandera triangular en la cima del poste (3 vértices)
            flag_pts = [
                (tx,      ty),       # vértice izquierdo superior (base de la bandera)
                (tx + 24, ty + 12),  # vértice derecho (punta)
                (tx,      ty + 24),  # vértice izquierdo inferior (base de la bandera)
            ]
            pygame.draw.polygon(surface, _CHECKPOINT_FLAG, flag_pts)

    def _render_vehicle(self, surface: pygame.Surface) -> None:
        """
        Dibuja ruedas (círculos con rayo) y chasis (rectángulo rotado).

        El rayo (spoke) en cada rueda indica la rotación actual: sin él,
        los círculos grises parecen estáticos aunque estén girando.
        """
        # Ruedas
        for wheel_body in (self._vehicle.back_wheel, self._vehicle.front_wheel):
            sx, sy = self._camera.world_to_screen(*wheel_body.position)
            cx, cy = int(sx), int(sy)

            pygame.draw.circle(surface, _WHEEL_COL, (cx, cy), WHEEL_RADIUS)
            pygame.draw.circle(surface, _WHEEL_RIM,  (cx, cy), WHEEL_RADIUS, 3)

            # Rayo para visualizar la rotación (70% del radio)
            end_x = cx + int(WHEEL_RADIUS * 0.7 * math.cos(wheel_body.angle))
            end_y = cy + int(WHEEL_RADIUS * 0.7 * math.sin(wheel_body.angle))
            pygame.draw.line(surface, _WHEEL_RIM, (cx, cy), (end_x, end_y), 2)

        # Chasis rotado
        sx, sy = self._camera.world_to_screen(*self._vehicle.chassis.position)
        pts  = _rotated_box(sx, sy, CHASSIS_WIDTH, CHASSIS_HEIGHT,
                            self._vehicle.chassis.angle)
        ipts = [(int(x), int(y)) for x, y in pts]
        pygame.draw.polygon(surface, _CHASSIS_COL,  ipts)
        pygame.draw.polygon(surface, _CHASSIS_EDGE, ipts, 2)

    def _render_player(self, surface: pygame.Surface) -> None:
        """Dibuja el conductor como rectángulo azul rotado sobre el chasis."""
        sx, sy = self._camera.world_to_screen(*self._player.body.position)
        pts  = _rotated_box(sx, sy, PLAYER_WIDTH, PLAYER_HEIGHT,
                            self._player.body.angle)
        ipts = [(int(x), int(y)) for x, y in pts]
        pygame.draw.polygon(surface, _PLAYER_COL, ipts)