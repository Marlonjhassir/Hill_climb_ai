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
from pathlib import Path

import numpy as np
import pygame
import torch

from ai.genome import Genome
from config.settings import FPS, MODEL_DIR, SCREEN_HEIGHT, SCREEN_WIDTH
from game.environment import Environment

# Segundos que la pantalla permanece congelada al terminar el episodio,
# para que el jugador pueda ver la posición final antes del reinicio.
_RESET_DELAY_S = 1.0


def _parse_args() -> argparse.Namespace:
    """
    Lee los argumentos de la línea de comandos.

    Returns:
        Namespace con atributos:
            mode (str): modo de ejecución.
            seed (int): semilla del terreno para reproducibilidad.
    """
    parser = argparse.ArgumentParser(
        description="Hill Climb AI — juego con física y aprendizaje neuroevolutivo."
    )
    parser.add_argument(
        "--mode",
        choices=["play", "train", "random_ai", "watch"],
        default="play",
        help=(
            "'play' para control manual, "
            "'random_ai' para ver una red con pesos aleatorios, "
            "'watch' para ver el mejor genoma entrenado (carga best_genome.pt), "
            "'train' para entrenamiento neuroevolutivo."
        ),
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


def _load_best_genome() -> tuple[Genome, float, int]:
    """
    Carga el mejor genoma entrenado desde MODEL_DIR/best_genome.pt.

    Si el archivo no existe, imprime un mensaje claro y termina el proceso
    con código de error 1. No tiene sentido arrancar el modo watch sin un
    genoma previamente entrenado.

    Qué hace torch.load():
        Deserializa el dict que guardamos en trainer._save_checkpoint():
        {'weights': torch.Tensor(470,), 'fitness': float, 'generation': int}.
        Es pickle especializado de PyTorch; reconoce tensores guardados con
        torch.save() y los reconstruye en memoria sin pasar por numpy.

    Returns:
        (genome, fitness, generation): el Genome reconstruido y sus metadatos.
    """
    best_path = Path(MODEL_DIR) / "best_genome.pt"

    if not best_path.exists():
        # Mensaje accionable: le decimos exactamente cómo solucionar el problema.
        print(
            f"[watch] Error: no se encontró '{best_path}'.\n"
            f"        Primero entrena con: python main.py --mode train"
        )
        sys.exit(1)

    # weights_only=False porque el dict guardado contiene escalares Python
    # (float, int) además del tensor de pesos. PyTorch >= 2.0 requiere
    # especificarlo explícitamente para evitar el warning; es seguro aquí
    # porque el archivo lo generamos nosotros mismos en trainer.py.
    data = torch.load(best_path, weights_only=False)

    genome = Genome()

    # data['weights'] es torch.Tensor (470,); set_weights() espera np.ndarray.
    # .numpy() comparte el buffer de memoria con el tensor (sin copia) cuando
    # el tensor está en CPU, que es siempre nuestro caso en este proyecto.
    genome.set_weights(data['weights'].numpy())

    fitness:    float = float(data['fitness'])
    generation: int   = int(data['generation'])

    print(
        f"[watch] Genoma cargado — generación {generation}, "
        f"fitness {fitness:.1f}"
    )
    return genome, fitness, generation


def main() -> None:
    """
    Game loop principal. Inicializa pygame, corre el juego y sale limpiamente.

    Flujo por frame:
      1. Vaciar la cola de eventos del sistema (QUIT, etc.).
      2. clock.tick(FPS) → mide el dt real de este frame.
      3. Si estamos en pausa post-episodio: renderizar y contar tiempo.
      4. Leer teclado / red neuronal → acción.
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

    # ------------------------------------------------------------------
    # Selección del controlador según el modo
    # ------------------------------------------------------------------
    # 'play'      → teclado (genome=None, se lee pygame.key.get_pressed()).
    # 'random_ai' → Genome con pesos Kaiming aleatorios, sin entrenar.
    # 'watch'     → mejor Genome guardado en disco por trainer.py.
    # Los tres modos comparten el mismo game loop; la diferencia es solo
    # qué objeto genera la acción en cada frame.
    genome: Genome | None

    if args.mode == "random_ai":
        genome = Genome()

    elif args.mode == "watch":
        # _load_best_genome() hace sys.exit(1) si el archivo no existe,
        # así que si llegamos aquí el genoma está garantizado.
        genome, fitness, generation = _load_best_genome()

        # Actualizamos el título de la ventana con los metadatos del genoma,
        # para que el usuario sepa qué generación y fitness está observando.
        pygame.display.set_caption(
            f"Hill Climb AI — watch | gen {generation} | fitness {fitness:.0f}"
        )

    else:
        # 'play' y 'train' — en 'train' main.py no se usa; el entrenamiento
        # corre completamente en trainer.py en modo headless.
        genome = None

    # Estado del frame anterior para alimentar la red neuronal.
    # El primer frame usa ceros (el vehículo aún no se ha movido).
    current_state: np.ndarray = np.zeros(14, dtype=np.float32)

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
                # El nuevo episodio empieza con estado desconocido: reseteamos
                # a ceros para que la red no reciba valores del episodio anterior.
                current_state = np.zeros(14, dtype=np.float32)
            # Renderizamos el último frame durante la pausa para que la
            # pantalla no quede en negro; el jugador ve la posición final.
            env.render(surface)
            pygame.display.flip()
            continue   # saltamos el step normal hasta que se reinicie

        # Paso 4: construir acción — teclado en modo 'play', red en los demás.
        if genome is not None:
            # La red recibe el estado del frame anterior y devuelve (accel, brake).
            # genome.forward() retorna np.ndarray (2,); env.step() acepta cualquier
            # iterable de dos floats, así que no hace falta conversión explícita.
            action = genome.forward(current_state)
        else:
            keys = pygame.key.get_pressed()
            action = _build_action(keys)

        # Paso 5: avanzar la física un frame y capturar el nuevo estado.
        state, _reward, done, _info = env.step(action, dt)

        # Guardamos el estado para el próximo frame (solo lo usan los modos
        # con red neuronal, pero actualizarlo siempre no tiene costo apreciable).
        current_state = np.array(state, dtype=np.float32)

        # Paso 6: dibujar el frame sobre la surface
        env.render(surface)

        # Paso 7: intercambiar buffers → el frame recién dibujado aparece en pantalla
        pygame.display.flip()

        # Paso 8: si el episodio terminó, comenzar la pausa antes del reinicio
        if done:
            waiting_reset = True


if __name__ == "__main__":
    main()