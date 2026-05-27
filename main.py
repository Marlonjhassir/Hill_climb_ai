"""
main.py — Punto de entrada del juego Hill Climb AI.

Responsabilidades:
  - Inicializar pygame y crear la ventana.
  - Correr el game loop: leer teclado → step → render → flip.
  - Reiniciar el episodio automáticamente cuando done=True.
  - Parsear --mode y --seed desde la terminal.

Prohibido: contener física, lógica de IA, dibujar directamente.
           Toda esa lógica vive en game/environment.py.
"""

import argparse
import sys

import pygame

from config.settings import FPS, SCREEN_HEIGHT, SCREEN_WIDTH
from game.environment import Environment

# Segundos que la pantalla permanece congelada al terminar el episodio,
# para que el jugador pueda ver la posición final antes del reinicio.
_RESET_DELAY_S = 1.0


def _parse_args() -> argparse.Namespace:
    """
    Lee los argumentos de la línea de comandos.

    Returns:
        Namespace con atributos:
            mode (str): 'play' (manual) o 'train' (futuro Fase 6).
            seed (int): semilla del terreno para reproducibilidad.
    """
    parser = argparse.ArgumentParser(
        description="Hill Climb AI — juego con física y aprendizaje neuroevolutivo."
    )
    parser.add_argument(
        "--mode",
        choices=["play", "train"],
        default="play",
        help="'play' para control manual, 'train' para IA (Fase 6).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Semilla del terreno. Mismo número = mismo mapa.",
    )
    return parser.parse_args()


def _build_action(keys: pygame.key.ScancodeWrapper) -> tuple[float, float]:
    """
    Convierte el estado actual del teclado en una acción (accel, brake).

    La IA en fases posteriores generará valores continuos en [0.0, 1.0].
    El teclado usa 0.0 o 1.0 (binario), suficiente para el modo manual.

    Teclas:
        D / Flecha derecha → acelerar
        A / Flecha izquierda → frenar

    Args:
        keys: resultado de pygame.key.get_pressed(), indexado por K_*.

    Returns:
        (accel, brake) ambos en {0.0, 1.0}.
    """
    # get_pressed() devuelve el ESTADO de cada tecla en este instante,
    # no un evento puntual. Esto es crucial: si el jugador mantiene 'D'
    # apretada durante 3 segundos, cada frame devolverá accel=1.0,
    # mientras que un evento KEYDOWN solo se dispararía una vez.
    accel = 1.0 if (keys[pygame.K_d] or keys[pygame.K_RIGHT]) else 0.0
    brake = 1.0 if (keys[pygame.K_a] or keys[pygame.K_LEFT]) else 0.0
    return accel, brake


def main() -> None:
    """
    Game loop principal. Inicializa pygame, corre el juego y sale limpiamente.

    Flujo por frame:
      1. Vaciar la cola de eventos del sistema (QUIT, etc.).
      2. clock.tick(FPS) → mide el dt real de este frame.
      3. Si estamos en pausa post-episodio: renderizar y contar tiempo.
      4. Leer teclado → acción.
      5. env.step(action, dt) → avanza la simulación.
      6. env.render(surface) → dibuja el frame.
      7. pygame.display.flip() → muestra el frame en pantalla.
      8. Si done: entrar en pausa → reset cuando expire el timer.
    """
    args = _parse_args()

    # ------------------------------------------------------------------
    # Inicialización de pygame
    # ------------------------------------------------------------------
    pygame.init()

    # set_mode crea la ventana y devuelve la Surface principal.
    # Esta Surface es el "lienzo" donde se dibujan todos los elementos.
    # Todo lo que pintemos sobre ella solo se hace visible después de flip().
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Hill Climb AI")

    # Clock controla el framerate.
    # clock.tick(FPS): duerme lo necesario para no superar FPS fotogramas/s
    # y devuelve los milisegundos reales transcurridos (puede ser > 1000/FPS
    # si el CPU estuvo ocupado con otra tarea).
    clock = pygame.time.Clock()

    env = Environment(seed=args.seed)

    # Acumulador para la pausa al final del episodio
    reset_timer: float = 0.0
    waiting_reset: bool = False

    # ------------------------------------------------------------------
    # Game loop — corre indefinidamente hasta que el usuario cierre la ventana
    # ------------------------------------------------------------------
    while True:

        # Paso 1: vaciar la cola de eventos del SO.
        # Si no llamamos a event.get() en cada frame, el sistema operativo
        # interpreta que el programa está colgado y marca la ventana como
        # "(No responde)" después de unos segundos.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # pygame.quit() apaga los submódulos (libera recursos de audio,
                # display, etc.). sys.exit() termina el proceso Python.
                # Solo con pygame.quit() el proceso Python seguiría corriendo.
                pygame.quit()
                sys.exit()

        # Paso 2: medir el tiempo real de este frame.
        # La conversión /1000.0 es necesaria porque tick() devuelve milisegundos
        # y env.step() espera segundos. Un frame a 60 FPS = ~16.67 ms = ~0.01667 s.
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0

        # Paso 3: gestión de pausa post-episodio.
        if waiting_reset:
            reset_timer += dt
            if reset_timer >= _RESET_DELAY_S:
                env.reset()
                waiting_reset = False
                reset_timer = 0.0
            # Renderizamos el último frame durante la pausa para que la
            # pantalla no quede en negro; el jugador ve la posición final.
            env.render(surface)
            pygame.display.flip()
            continue   # saltamos el step normal hasta que se reinicie

        # Paso 4: leer teclado → construir acción
        keys = pygame.key.get_pressed()
        action = _build_action(keys)

        # Paso 5: avanzar la física un frame
        # Ignoramos state y reward por ahora (stubs hasta Fases 4 y 3).
        _state, _reward, done, _info = env.step(action, dt)

        # Paso 6: dibujar el frame sobre la surface
        env.render(surface)

        # Paso 7: intercambiar buffers → el frame recién dibujado aparece en pantalla
        pygame.display.flip()

        # Paso 8: si el episodio terminó, comenzar la pausa antes del reinicio
        if done:
            waiting_reset = True


if __name__ == "__main__":
    main()