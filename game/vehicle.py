"""
game/vehicle.py — Implementación física del vehículo en pymunk.

Responsabilidades:
  - Crear chasis (cuerpo rectangular dinámico) y dos ruedas (cuerpos circulares).
  - Unir ruedas al chasis con PivotJoint (suspensión rígida).
  - Aplicar torque mediante SimpleMotor en cada rueda.
  - Exponer accelerate(), brake(), update() y get_telemetry().

Prohibido: dibujar, leer inputs de teclado, contener lógica de episodio.
"""

import pymunk

from config.settings import CHASSIS_MASS, WHEEL_MASS, WHEEL_FRICTION
from game.physics import COLLISION_CHASSIS, COLLISION_WHEEL, VEHICLE_GROUP

# ---------------------------------------------------------------------------
# Constantes del vehículo
# ---------------------------------------------------------------------------
# No están en settings.py porque el plan maestro no las lista allí; se definen
# aquí para mantenerlas cerca del código que las usa. Si en el futuro se
# necesita ajustarlas desde experimentos, se pueden mover a settings.py.

WHEEL_RADIUS   = 25     # px — radio de cada rueda (disco sólido)
CHASSIS_WIDTH  = 100    # px — ancho del chasis
CHASSIS_HEIGHT = 35     # px — alto del chasis
WHEEL_OFFSET_X = 45     # px — separación horizontal entre centro del chasis y eje de rueda
WHEEL_OFFSET_Y = 22     # px — las ruedas cuelgan bajo el centro del chasis (Y↓ positivo)

MOTOR_MAX_FORCE   = 50000  # kg·px/s² — torque máximo que puede aplicar el motor
ACCELERATION_RATE = 15.0   # rad/s — velocidad angular objetivo al acelerar al 100%
BRAKE_RATE        = 8.0    # rad/s — velocidad angular objetivo al frenar al 100%


class Vehicle:
    """
    Vehículo físico de dos ruedas impulsado por torque.

    Uso típico desde environment.py:
        vehicle = Vehicle(space=engine.get_space(), position=(100, 455))
        vehicle.accelerate(1.0)
        vehicle.update(dt)
        # ... engine.step(dt) ...
        telemetry = vehicle.get_telemetry()
    """

    def __init__(self, space: pymunk.Space, position: tuple[float, float]) -> None:
        """
        Args:
            space:    Space activo de PhysicsEngine.
            position: coordenadas (x, y) del centro del chasis al nacer.
                      Calcular desde environment.py como:
                      y = terrain.height_at(x) - WHEEL_OFFSET_Y - WHEEL_RADIUS
        """
        self._accel_intensity: float = 0.0
        self._brake_intensity: float = 0.0

        # Flags de contacto con el suelo — los actualiza environment.py
        # después de leer los eventos de colisión de PhysicsEngine.
        # back  = rueda trasera (izquierda, menor x) = input 5 de la IA
        # front = rueda delantera (derecha, mayor x) = input 6 de la IA
        self.back_wheel_contact: bool = False
        self.front_wheel_contact: bool = False

        self._setup_bodies(position)
        self._setup_joints()
        self._setup_motors()
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Construcción interna
    # ------------------------------------------------------------------

    def _setup_bodies(self, pos: tuple[float, float]) -> None:
        """Crea los tres cuerpos dinámicos (chasis + 2 ruedas) con sus shapes."""
        cx, cy = pos

        # --- Chasis ---------------------------------------------------
        # moment_for_box calcula el momento de inercia de un rectángulo macizo.
        # Es el equivalente rotacional de la masa: cuánto cuesta rotar el objeto.
        # Un chasis ancho resiste más la inclinación que uno estrecho.
        chassis_moment = pymunk.moment_for_box(
            CHASSIS_MASS, (CHASSIS_WIDTH, CHASSIS_HEIGHT)
        )
        self.chassis = pymunk.Body(CHASSIS_MASS, chassis_moment)
        self.chassis.position = (cx, cy)

        # Poly.create_box: rectángulo centrado en el body.
        # La shape vive en coordenadas locales del body; cuando el body
        # se mueve o rota, la shape lo sigue automáticamente.
        self.chassis_shape = pymunk.Poly.create_box(
            self.chassis, (CHASSIS_WIDTH, CHASSIS_HEIGHT)
        )
        self.chassis_shape.collision_type = COLLISION_CHASSIS
        # Fricción baja: si el chasis roza el suelo en una pendiente extrema,
        # no queremos que la fricción lo trabe.
        self.chassis_shape.friction = 0.3

        # --- Ruedas ---------------------------------------------------
        # moment_for_circle(mass, inner_radius, outer_radius):
        # inner_radius = 0 → disco macizo (sólido), no un aro.
        # Si inner_radius > 0, sería un cilindro hueco (más fácil de rotar).
        wheel_moment = pymunk.moment_for_circle(WHEEL_MASS, 0, WHEEL_RADIUS)

        # Rueda trasera — a la izquierda y por debajo del centro del chasis
        self.back_wheel = pymunk.Body(WHEEL_MASS, wheel_moment)
        self.back_wheel.position = (cx - WHEEL_OFFSET_X, cy + WHEEL_OFFSET_Y)

        self.back_wheel_shape = pymunk.Circle(self.back_wheel, WHEEL_RADIUS)
        self.back_wheel_shape.friction = WHEEL_FRICTION
        self.back_wheel_shape.collision_type = COLLISION_WHEEL

        # Rueda delantera — a la derecha y por debajo del centro del chasis
        self.front_wheel = pymunk.Body(WHEEL_MASS, wheel_moment)
        self.front_wheel.position = (cx + WHEEL_OFFSET_X, cy + WHEEL_OFFSET_Y)

        self.front_wheel_shape = pymunk.Circle(self.front_wheel, WHEEL_RADIUS)
        self.front_wheel_shape.friction = WHEEL_FRICTION
        self.front_wheel_shape.collision_type = COLLISION_WHEEL

        # ShapeFilter: chasis y ruedas están en el mismo grupo → pymunk NO
        # calcula colisiones entre ellas. Sin este filtro, las ruedas (radio=25)
        # se solapan con el chasis (offset=22 < 17.5+25=42.5) y pymunk aplica
        # impulsos de separación enormes en cada frame, desestabilizando el vehículo.
        _vf = pymunk.ShapeFilter(group=VEHICLE_GROUP)
        self.chassis_shape.filter    = _vf
        self.back_wheel_shape.filter = _vf
        self.front_wheel_shape.filter = _vf

    def _setup_joints(self) -> None:
        """
        Conecta cada rueda al chasis con un PivotJoint.

        PivotJoint(body_a, body_b, pivot_mundo):
          - Acepta el pivot en coordenadas MUNDO y pymunk lo convierte
            internamente a coordenadas locales de cada body.
          - Efecto: el centro de la rueda queda fijo respecto al chasis.
            Si el chasis se inclina, la rueda se mueve con él.
          - Los bodies pueden ROTAR libremente entre sí: la rueda puede
            girar sobre su eje sin que el joint lo impida.

        Por qué no PinJoint:
          PinJoint solo mantiene distancia fija entre dos puntos. Con una
          sola restricción de distancia, la rueda podría oscilar como
          péndulo alrededor del eje — no queremos eso en una suspensión.
        """
        self._back_joint = pymunk.PivotJoint(
            self.chassis,
            self.back_wheel,
            self.back_wheel.position,    # pivot en coords mundo al momento de creación
        )

        self._front_joint = pymunk.PivotJoint(
            self.chassis,
            self.front_wheel,
            self.front_wheel.position,
        )

    def _setup_motors(self) -> None:
        """
        Crea un SimpleMotor por rueda.

        SimpleMotor(body_a, body_b, rate):
          - Aplica torque para mantener (velocidad_angular(b) - velocidad_angular(a))
            = rate rad/s. Como referencia usamos el chasis (body_a), así el motor
            da tracción incluso cuando el chasis está inclinado en una pendiente.
          - rate > 0: rueda gira hacia adelante (vehículo avanza a la derecha).
          - rate < 0: rueda gira hacia atrás (frena o retrocede).

        IMPORTANTE: max_force = 0 por defecto → el motor no hace nada.
        Se ajusta en update() cuando hay input activo.
        """
        self._back_motor = pymunk.SimpleMotor(self.chassis, self.back_wheel, 0)
        self._back_motor.max_force = 0

        self._front_motor = pymunk.SimpleMotor(self.chassis, self.front_wheel, 0)
        self._front_motor.max_force = 0

    def _add_to_space(self, space: pymunk.Space) -> None:
        """
        Añade todos los elementos al Space de una vez.

        Hay que añadir tanto los Body como sus Shape: si añades solo la Shape,
        el cuerpo no participa en la simulación física (no recibe fuerzas).
        Los constraints (joints, motores) se añaden igual que los bodies.
        """
        space.add(
            self.chassis,        self.chassis_shape,
            self.back_wheel,     self.back_wheel_shape,
            self.front_wheel,    self.front_wheel_shape,
            self._back_joint,    self._front_joint,
            self._back_motor,    self._front_motor,
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def accelerate(self, intensity: float) -> None:
        """
        Establece la intensidad de aceleración hacia adelante.

        Args:
            intensity: [0.0, 1.0]. 1.0 = torque máximo hacia adelante.
        """
        self._accel_intensity = max(0.0, min(1.0, intensity))

    def brake(self, intensity: float) -> None:
        """
        Establece la intensidad de frenado / marcha atrás.

        Args:
            intensity: [0.0, 1.0]. 1.0 = torque máximo hacia atrás.
        """
        self._brake_intensity = max(0.0, min(1.0, intensity))

    def update(self, _dt: float) -> None:
        """
        Aplica los inputs de control a los motores para el próximo step.

        La resultante: accel_intensity - brake_intensity.
        Si ambas son iguales, se anulan → rueda libre.
        Si no hay input (net ≈ 0), max_force = 0 → sin resistencia del motor,
        el vehículo puede rodar libremente por una pendiente (comportamiento
        más natural que frenar automáticamente).

        Args:
            _dt: delta de tiempo. No se usa aquí (pymunk gestiona el tiempo
                 internamente), pero la firma lo requiere por consistencia
                 con el protocolo de update() de todos los módulos.
        """
        net = self._accel_intensity - self._brake_intensity

        if abs(net) > 0.01:
            # El signo negativo es CRÍTICO: en pymunk con Y positivo hacia abajo,
            # velocidad angular positiva = giro antihorario visualmente = la parte
            # inferior de la rueda va a la DERECHA = fricción empuja el vehículo
            # a la IZQUIERDA (retroceso). Negando, logramos avance correcto con D.
            rate  = -ACCELERATION_RATE * net
            force = MOTOR_MAX_FORCE
        else:
            # Sin input activo: desactivar el motor (ruedas libres)
            rate  = 0.0
            force = 0.0

        self._back_motor.rate      = rate
        self._back_motor.max_force = force

        # La rueda delantera recibe el 60% de la fuerza.
        # Tracción principalmente trasera: más estable en pendientes y
        # más realista para un vehículo tipo Hill Climb Racing.
        self._front_motor.rate      = rate
        self._front_motor.max_force = force * 0.6

    # ------------------------------------------------------------------
    # Telemetría
    # ------------------------------------------------------------------

    def get_telemetry(self) -> dict:
        """
        Devuelve el estado físico actual del vehículo.

        Los valores de velocidad y ángulo son los que la IA usará como
        parte de su vector de estado de 14 entradas (Fase 4).

        Returns:
            dict con claves:
              vx    — velocidad horizontal del chasis (px/s)
              vy    — velocidad vertical del chasis (px/s)
              angle — ángulo del chasis en radianes (positivo = horario)
              omega — velocidad angular del chasis (rad/s)
              back_contact  — True si la rueda trasera toca el suelo
              front_contact — True si la rueda delantera toca el suelo
        """
        vel = self.chassis.velocity
        return {
            'vx':           vel.x,
            'vy':           vel.y,
            'angle':        self.chassis.angle,
            'omega':        self.chassis.angular_velocity,
            'back_contact': self.back_wheel_contact,
            'front_contact':self.front_wheel_contact,
        }