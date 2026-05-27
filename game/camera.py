"""
game/camera.py — Transformación de coordenadas mundo → pantalla.

Responsabilidades:
  - Mantener la posición de la "ventana" que se muestra en pantalla.
  - Seguir al vehículo con lerp suave en X e Y.
  - Transformar coordenadas de mundo a pantalla y viceversa.

Prohibido: contener lógica de juego, dibujar nada, acceder al Space de pymunk.
"""

from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT

# Factor de lerp: controla la velocidad de seguimiento de la cámara.
# Valor alto → la cámara "atrapa" al vehículo rápido (más rígida).
# Valor bajo → la cámara lo sigue con más inercia (más cinematográfica).
# Con 5.0 y dt ≈ 1/60, cada frame la cámara recorre ≈ 8% de la distancia
# restante — suficientemente suave para no marear y suficientemente rápida
# para no perder al vehículo de vista.
LERP_FACTOR = 5.0


class Camera:
    """
    Cámara 2D con seguimiento suavizado por lerp.

    Internamente mantiene (self.x, self.y): la coordenada del mundo que
    corresponde a la esquina superior izquierda de la pantalla.

    Uso típico desde environment.py en cada frame:
        camera.update(vehicle.chassis.position.x,
                      vehicle.chassis.position.y, dt)
        sx, sy = camera.world_to_screen(wx, wy)
        pygame.draw.circle(surface, color, (int(sx), int(sy)), radius)
    """

    def __init__(self) -> None:
        # Posición inicial de la cámara en coordenadas mundo.
        # x=0, y=0 significa que se ve la esquina superior izquierda del mundo.
        # Se ajustará en el primer update() para centrarse sobre el vehículo.
        self.x: float = 0.0
        self.y: float = 0.0

    def update(self, target_x: float, target_y: float, dt: float) -> None:
        """
        Acerca la cámara hacia el objetivo con lerp.

        El objetivo de la cámara es que el vehículo quede en el centro
        de la pantalla. Para eso, el borde izquierdo (camera.x) debe ser
        target_x - SCREEN_WIDTH/2, y el borde superior (camera.y) debe
        ser target_y - SCREEN_HEIGHT/2.

        La fórmula de lerp:
            nueva_pos = actual + (objetivo - actual) * FACTOR * dt

        Con dt variable (no siempre exactamente 1/60), multiplicar por dt
        hace que la velocidad de la cámara sea independiente del framerate:
        a 30 FPS o a 120 FPS, la cámara tarda el mismo tiempo en alcanzar
        el objetivo. Sin este dt, a más FPS la cámara iría más rápido.

        Args:
            target_x: coordenada x del vehículo en mundo (px).
            target_y: coordenada y del vehículo en mundo (px).
            dt:       tiempo del frame en segundos (ej. 1/60 ≈ 0.0167).
        """
        # Coordenadas del borde superior-izquierdo que centrarían al vehículo
        target_cam_x = target_x - SCREEN_WIDTH  / 2
        target_cam_y = target_y - SCREEN_HEIGHT / 2

        # Lerp: la cámara se acerca al objetivo proporcionalmente a la distancia
        self.x += (target_cam_x - self.x) * LERP_FACTOR * dt
        self.y += (target_cam_y - self.y) * LERP_FACTOR * dt

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """
        Convierte coordenadas de mundo a coordenadas de pantalla.

        Un objeto en world_x = camera.x + 300 aparece en screen_x = 300.
        Si la cámara se ha desplazado hacia la derecha (camera.x > 0),
        los objetos a la izquierda quedan con screen_x negativo (fuera de
        pantalla) y no hay que dibujarlos.

        Args:
            wx: coordenada x en mundo (px).
            wy: coordenada y en mundo (px).

        Returns:
            (screen_x, screen_y) — usar int() al pasarlos a pygame.
        """
        return (wx - self.x, wy - self.y)

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """
        Convierte coordenadas de pantalla a coordenadas de mundo.

        Operación inversa a world_to_screen. Útil para saber en qué punto
        del mundo el usuario hizo clic con el ratón (en fases posteriores).

        Args:
            sx: coordenada x en pantalla (px).
            sy: coordenada y en pantalla (px).

        Returns:
            (world_x, world_y).
        """
        return (sx + self.x, sy + self.y)