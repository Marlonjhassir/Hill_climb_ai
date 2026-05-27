"""
game/ui.py — HUD (Heads-Up Display) del juego.

Responsabilidades:
  - Dibujar panel de información: score, distancia, tiempo, generación, mejor fitness.
  - Dibujar barra de tiempo con código de color (verde → amarillo → rojo).

Prohibido: modificar estado del juego, leer inputs, acceder a pymunk.
Este módulo SOLO recibe valores y los renderiza. Es completamente pasivo.
"""

import pygame

from config.settings import SCREEN_WIDTH, MAX_TIME

# ---------------------------------------------------------------------------
# Dimensiones y posición del panel principal
# ---------------------------------------------------------------------------
PANEL_X = 10       # px desde el borde izquierdo de la pantalla
PANEL_Y = 10       # px desde el borde superior
PANEL_W = 295      # px de ancho del panel
PANEL_H = 155      # px de alto del panel

# Barra de tiempo: justo debajo del panel
BAR_X = PANEL_X
BAR_Y = PANEL_Y + PANEL_H + 4
BAR_W = PANEL_W
BAR_H = 10

# ---------------------------------------------------------------------------
# Paleta de colores
# ---------------------------------------------------------------------------
COLOR_TEXT       = (255, 255, 255)       # blanco — valores principales
COLOR_LABEL      = (170, 190, 220)       # azul claro — etiquetas
COLOR_PANEL_BG   = (0,   0,   0,   155) # negro semitransparente (RGBA)
COLOR_BAR_BG     = (55,  55,  55,  180) # gris oscuro semitransparente
COLOR_BAR_OK     = (55,  200, 55)        # verde — tiempo > 50 %
COLOR_BAR_WARN   = (220, 180, 0)         # amarillo — tiempo 20–50 %
COLOR_BAR_LOW    = (220, 50,  50)        # rojo — tiempo < 20 %


class UI:
    """
    HUD estático: recibe valores, los pinta, no guarda estado de juego.

    Uso típico desde environment.py en cada frame:
        ui.draw(
            score=self.score,
            distance=self.max_distance,
            time_left=self.time_left,
        )
    """

    def __init__(self, surface: pygame.Surface) -> None:
        """
        Args:
            surface: la Surface principal de pygame (la ventana del juego).
                     Sobre ella se dibujan todos los elementos del HUD.
        """
        # pygame.font.init() es seguro llamarlo varias veces; solo inicializa
        # el módulo de fuentes si aún no está activo.
        pygame.font.init()

        self._surface = surface

        # SysFont("monospace", size): busca una fuente monoespaciada del sistema.
        # Las fuentes monoespaciadas alinean valores numéricos de forma limpia
        # en el HUD (todos los dígitos tienen el mismo ancho).
        self._font_label = pygame.font.SysFont("monospace", 13)
        self._font_value = pygame.font.SysFont("monospace", 18, bold=True)

        # Fondos semitransparentes creados UNA VEZ y reutilizados en cada frame.
        # pygame.SRCALPHA habilita el canal alfa en la Surface (transparencia).
        # Sin este flag, fill((r,g,b,a)) ignoraría el valor 'a' y pintaría opaco.
        self._panel_surf = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
        self._panel_surf.fill(COLOR_PANEL_BG)

        self._bar_bg_surf = pygame.Surface((BAR_W, BAR_H), pygame.SRCALPHA)
        self._bar_bg_surf.fill(COLOR_BAR_BG)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def draw(
        self,
        score: int,
        distance: float,
        time_left: float,
        generation: int = 1,
        best_fitness: float = 0.0,
    ) -> None:
        """
        Dibuja el HUD completo sobre la surface principal.

        Args:
            score:        monedas recogidas × su valor.
            distance:     distancia horizontal máxima alcanzada (px).
            time_left:    segundos restantes en el episodio.
            generation:   generación actual del algoritmo genético (1 en modo manual).
            best_fitness: mejor fitness histórico (0 en modo manual).
        """
        self._draw_panel(score, distance, time_left, generation, best_fitness)
        self._draw_time_bar(time_left)

    # ------------------------------------------------------------------
    # Métodos internos de renderizado
    # ------------------------------------------------------------------

    def _draw_panel(
        self,
        score: int,
        distance: float,
        time_left: float,
        generation: int,
        best_fitness: float,
    ) -> None:
        """Dibuja el panel informativo con etiquetas y valores."""

        # Fondo semitransparente: blit mezcla el alpha con lo que ya está
        # dibujado en self._surface (terreno, vehículo, etc.).
        self._surface.blit(self._panel_surf, (PANEL_X, PANEL_Y))

        # Filas: (etiqueta, valor_formateado)
        # El formato :.0f elimina decimales para distancia y fitness (son grandes).
        # El formato :.1f deja un decimal para el tiempo (más precisión útil).
        rows = [
            ("SCORE",      f"{score}"),
            ("DISTANCIA",  f"{distance:.0f} px"),
            ("TIEMPO",     f"{time_left:.1f} s"),
            ("GENERACION", f"{generation}"),
            ("MEJOR FIT",  f"{best_fitness:.0f}"),
        ]

        x      = PANEL_X + 12
        y      = PANEL_Y + 12
        row_h  = 27          # altura de cada fila en px
        val_x  = x + 118     # columna de los valores (alineada a la derecha del label)

        for label, value in rows:
            # font.render(texto, antialias, color) → Surface con el texto.
            # antialias=True suaviza los bordes de los caracteres (más legible).
            label_surf = self._font_label.render(label, True, COLOR_LABEL)
            value_surf = self._font_value.render(value, True, COLOR_TEXT)

            # blit(source, dest): copia 'source' sobre self._surface en 'dest'.
            self._surface.blit(label_surf, (x, y + 4))   # +4 para alinear baseline
            self._surface.blit(value_surf, (val_x, y))
            y += row_h

    def _draw_time_bar(self, time_left: float) -> None:
        """
        Dibuja la barra de tiempo debajo del panel informativo.

        ratio = time_left / MAX_TIME ∈ [0, 1]
        La barra se llena de izquierda a derecha proporcionalmente al ratio.
        El color cambia según el tiempo restante para alertar visualmente:
          > 50% → verde (tiempo de sobra)
          20-50% → amarillo (atención)
          < 20% → rojo (urgente)
        """
        # ratio acotado a [0, 1] para no dibujar barras fuera de rango
        ratio = max(0.0, min(1.0, time_left / MAX_TIME))

        # Fondo gris de la barra completa
        self._surface.blit(self._bar_bg_surf, (BAR_X, BAR_Y))

        # Color según urgencia
        if ratio > 0.5:
            color = COLOR_BAR_OK
        elif ratio > 0.2:
            color = COLOR_BAR_WARN
        else:
            color = COLOR_BAR_LOW

        # Relleno proporcional al tiempo restante
        fill_w = int(BAR_W * ratio)
        if fill_w > 0:
            # pygame.draw.rect(surface, color, (x, y, w, h))
            pygame.draw.rect(
                self._surface,
                color,
                (BAR_X, BAR_Y, fill_w, BAR_H),
            )