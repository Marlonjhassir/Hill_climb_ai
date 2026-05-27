"""
game/environment.py — Orquestador de todos los módulos del juego.

Responsabilidades:
  - Crear y conectar: PhysicsEngine, Terrain, Vehicle, Player, Camera, UI.
  - En step(): aplicar acción → avanzar física → leer eventos → actualizar estado.
  - En render(): dibujar todos los elementos en orden de capas (back-to-front).
  - Exponer get_state() (stub hasta Fase 4) y step() con interfaz tipo Gym.

Prohibido: contener física directa (delegar a PhysicsEngine), dibujar sin
transformar por la cámara, leer inputs de teclado (eso va en main.py).
"""

import math

import pygame

from config.settings import MAX_TIME, SCREEN_HEIGHT, SCREEN_WIDTH
from game.camera import Camera
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

# ---------------------------------------------------------------------------
# Paleta de colores para renderizado placeholder (sin sprites aún)
# ---------------------------------------------------------------------------
_SKY_COLOR    = (100, 160, 230)   # azul cielo
_GROUND_FILL  = (85,  65,  45)    # marrón tierra
_GROUND_LINE  = (110, 85,  60)    # marrón claro para la superficie
_WHEEL_COL    = (40,  40,  40)    # gris oscuro rueda
_WHEEL_RIM    = (200, 200, 200)   # gris claro llanta
_CHASSIS_COL  = (180, 50,  50)    # rojo chasis
_CHASSIS_EDGE = (230, 100, 100)   # rojo claro borde
_PLAYER_COL   = (50,  120, 220)   # azul conductor


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

        # Calcular spawn_y para que las ruedas queden justo sobre el suelo
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

        # Estado del episodio
        self.score: int          = 0
        self.max_distance: float = 0.0   # distancia horizontal desde spawn
        self.time_left: float    = MAX_TIME
        self.done: bool          = False

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
          3. Leer eventos  → player_touched_ground, etc.
          4. Actualizar estado → tiempo, distancia, score
          5. Actualizar cámara → lerp hacia el chasis

        Args:
            action: (accel, brake) ambos en [0.0, 1.0].
            dt:     delta de tiempo en segundos (ej. 1/60).

        Returns:
            state   — vector de 14 entradas (stub [] hasta Fase 4).
            reward  — recompensa del frame (stub 0.0 hasta Fase 3).
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

        # Paso 4: actualizar estado del episodio

        # Tiempo restante: se decrementa cada frame
        self.time_left = max(0.0, self.time_left - dt)
        if self.time_left == 0.0:
            self.done = True

        # Distancia: solo contamos el avance hacia la derecha (máximo histórico)
        # Resta spawn_x para que la distancia empiece en 0, no en 100.
        current_dist = self._vehicle.chassis.position.x - self._spawn_x
        if current_dist > self.max_distance:
            self.max_distance = current_dist

        # Paso 5: actualizar cámara para que siga al chasis
        chassis_pos = self._vehicle.chassis.position
        self._camera.update(chassis_pos.x, chassis_pos.y, dt)

        info = {
            'score':    self.score,
            'distance': self.max_distance,
            'time':     self.time_left,
        }
        return self.get_state(), self._compute_reward(), self.done, info

    def _compute_reward(self) -> float:
        """
        Stub de recompensa por frame.
        Implementación completa en Fase 3 usando ai/reward_system.py.
        """
        return 0.0

    def get_state(self) -> list[float]:
        """
        Stub del vector de estado de 14 entradas para la IA.
        Implementación completa en Fase 4.
        """
        return []

    # ------------------------------------------------------------------
    # Renderizado (back-to-front: lo primero dibujado queda detrás)
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        """
        Dibuja un frame completo sobre 'surface'.

        Orden de capas:
          1. Cielo (fondo completo)
          2. Terreno (detrás del vehículo)
          3. Ruedas + chasis
          4. Conductor
          5. HUD (encima de todo, sin transformación de cámara)
        """
        if self._ui is None:
            self._ui = UI(surface)

        # Capa 1: fondo
        surface.fill(_SKY_COLOR)

        # Capas 2-4: mundo (usa camera.world_to_screen para posicionar)
        self._render_terrain(surface)
        self._render_vehicle(surface)
        self._render_player(surface)

        # Capa 5: HUD (siempre en la misma posición de pantalla)
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
        # Convertir todos los puntos del terreno a coordenadas de pantalla
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
        pts = _rotated_box(sx, sy, CHASSIS_WIDTH, CHASSIS_HEIGHT,
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