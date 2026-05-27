"""
game/player.py — Conductor que va encima del chasis.

Responsabilidades:
  - Crear un cuerpo rígido pequeño posicionado sobre el chasis.
  - Mantenerlo rígidamente unido al chasis (PivotJoint + GearJoint).
  - Marcar su shape con COLLISION_PLAYER para que physics.py detecte
    cuando el conductor toca el suelo y active player_touched_ground.

Regla de juego: si el conductor toca el terreno → episodio terminado.
Quien aplica esa regla es environment.py; este módulo solo provee el cuerpo.
"""

import pymunk

from game.physics import COLLISION_PLAYER, VEHICLE_GROUP
from game.vehicle import CHASSIS_HEIGHT

# ---------------------------------------------------------------------------
# Constantes del conductor
# ---------------------------------------------------------------------------
PLAYER_WIDTH    = 20     # px — ancho de la silueta del conductor
PLAYER_HEIGHT   = 30     # px — alto de la silueta del conductor
PLAYER_MASS     = 0.8    # kg — masa pequeña; contribuye a la inercia del sistema
# Distancia vertical desde el centro del chasis hasta el centro del conductor.
# = mitad del chasis + mitad del conductor → quedan justo pegados.
PLAYER_OFFSET_Y = CHASSIS_HEIGHT / 2 + PLAYER_HEIGHT / 2


class Player:
    """
    Conductor físico unido rígidamente al chasis del vehículo.

    No necesita update() porque es pasivo: los joints sincronizan
    posición y rotación con el chasis automáticamente en cada step().

    Uso típico desde environment.py:
        player = Player(space=engine.get_space(), chassis=vehicle.chassis)
        # Después de engine.step(dt):
        if engine.player_touched_ground:
            done = True
    """

    def __init__(self, space: pymunk.Space, chassis: pymunk.Body) -> None:
        """
        Args:
            space:   Space activo de PhysicsEngine.
            chassis: Body del chasis (vehicle.chassis). El conductor se
                     posiciona encima de él y queda ligado por joints.
        """
        self._setup_body(chassis)
        self._setup_constraints(chassis)
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Construcción interna
    # ------------------------------------------------------------------

    def _setup_body(self, chassis: pymunk.Body) -> None:
        """Crea el body del conductor y su shape con collision_type PLAYER."""
        # El conductor nace directamente encima del centro del chasis.
        # PLAYER_OFFSET_Y es positivo pero lo restamos porque Y↓ positivo
        # significa "abajo"; el conductor está ARRIBA, es decir, en y menor.
        player_x = chassis.position.x
        player_y = chassis.position.y - PLAYER_OFFSET_Y

        moment = pymunk.moment_for_box(PLAYER_MASS, (PLAYER_WIDTH, PLAYER_HEIGHT))
        self.body = pymunk.Body(PLAYER_MASS, moment)
        self.body.position = (player_x, player_y)
        # Iniciar con el mismo ángulo que el chasis (normalmente 0 al nacer)
        self.body.angle = chassis.angle

        # Shape: rectángulo pequeño que representa la silueta del conductor.
        self.shape = pymunk.Poly.create_box(self.body, (PLAYER_WIDTH, PLAYER_HEIGHT))
        self.shape.collision_type = COLLISION_PLAYER

        # Fricción cero: si el conductor toca el suelo (fin de episodio),
        # no queremos que la fricción aplique fuerzas laterales extrañas
        # al chasis en ese último frame de contacto.
        self.shape.friction = 0.0

        # Mismo grupo que el vehículo: el conductor no colisiona con el chasis
        # ni las ruedas (ya están unidos por joints y se solapan geométricamente).
        # Sí sigue colisionando con el terreno (grupo 0) → condición de game over.
        self.shape.filter = pymunk.ShapeFilter(group=VEHICLE_GROUP)

    def _setup_constraints(self, chassis: pymunk.Body) -> None:
        """
        Dos joints para una unión rígida completa con el chasis.

        Por qué necesitamos DOS joints:
          Un PivotJoint solo restringe POSICIÓN: el conductor no se aleja
          del eje, pero puede girar libremente (como un dedo pinchado en un
          tablero: no se mueve pero puede rotar).
          El GearJoint restringe ROTACIÓN: fuerza al conductor a girar
          exactamente al mismo ritmo que el chasis.
          Juntos simulan una soldadura rígida.
        """
        # PivotJoint en la posición actual del conductor (coordenadas mundo).
        # pymunk convierte este punto a coords locales de cada body internamente.
        self._pivot = pymunk.PivotJoint(
            chassis,
            self.body,
            self.body.position,    # pivot fijo en el centro del conductor
        )

        # GearJoint(a, b, phase, ratio):
        #   Fuerza: angular_velocity(b) = angular_velocity(a) * ratio
        #   ratio = 1.0 → rotan al mismo ritmo.
        #   phase = 0   → parten con el mismo ángulo base.
        self._gear = pymunk.GearJoint(chassis, self.body, phase=0, ratio=1.0)

    def _add_to_space(self, space: pymunk.Space) -> None:
        """Añade body, shape y ambos constraints al Space."""
        space.add(
            self.body,
            self.shape,
            self._pivot,
            self._gear,
        )

    # ------------------------------------------------------------------
    # Acceso
    # ------------------------------------------------------------------

    @property
    def position(self) -> pymunk.Vec2d:
        """Posición actual del conductor en coordenadas de mundo."""
        return self.body.position