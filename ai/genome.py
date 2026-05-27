"""
ai/genome.py — Individuo de la población evolutiva.

Responsabilidades:
  - Encapsular una PolicyNet y su fitness dentro de un único objeto manejable.
  - Exponer get_weights() / set_weights() como interfaz para GeneticAlgorithm.
  - Implementar mutate() y copy() para que GeneticAlgorithm los invoque.
  - Exponer forward() para que trainer.py pueda ejecutar un episodio sin
    importar torch directamente.

Prohibido: contener lógica de selección, crossover o gestión de población
(eso es responsabilidad de genetic_algorithm.py).
"""

import copy

import numpy as np
import torch

from ai.neural_network import PolicyNet
from config.settings import MUTATION_RATE, MUTATION_SIGMA


class Genome:
    """
    Individuo de la población evolutiva.

    Un Genome es la unidad que el algoritmo genético crea, evalúa, selecciona
    y transforma. Contiene:
      - Una PolicyNet (la red que controla el vehículo).
      - Un escalar de fitness (cuán bien condujo en el último episodio).

    Los pesos de la red se manejan internamente como un vector NumPy 1D para
    que los operadores evolutivos (crossover, mutación) sean simples operaciones
    sobre arrays, sin necesidad de conocer la arquitectura de la red.

    Example:
        >>> g = Genome()
        >>> estado = np.zeros(14, dtype=np.float32)
        >>> accion = g.forward(estado)   # array (2,) en [0, 1]
        >>> g.mutate()
        >>> g2 = g.copy()
        >>> g2.fitness = 0.0             # reset al clonar para nueva evaluación
    """

    def __init__(self) -> None:
        # PolicyNet con pesos inicializados por Kaiming (default de nn.Linear).
        # Kaiming distribuye los pesos como U(-1/√n_in, 1/√n_in), lo que evita
        # que todas las neuronas de una capa partan del mismo valor (simetría
        # perfecta) y garantiza diversidad real en la primera generación.
        self.net: PolicyNet = PolicyNet()

        # Fitness del episodio más reciente. El algoritmo genético lo escribe
        # después de evaluar al individuo en el entorno.
        # Fórmula (ver plan maestro): distancia_max + 50 * monedas_recogidas.
        self.fitness: float = 0.0

    # ------------------------------------------------------------------
    # Interfaz de pesos — delega en PolicyNet
    # ------------------------------------------------------------------

    def get_weights(self) -> np.ndarray:
        """
        Devuelve los pesos de la red como vector 1D NumPy float32 (copia).

        Returns:
            np.ndarray de shape (n_params,). Para la arquitectura 14→16→12→2,
            n_params = 470.
        """
        return self.net.get_weights()

    def set_weights(self, weights: np.ndarray) -> None:
        """
        Inyecta un vector de pesos 1D en la red.

        Args:
            weights: np.ndarray de shape (n_params,), dtype float32.
        """
        self.net.set_weights(weights)

    # ------------------------------------------------------------------
    # Forward pass — interfaz sin torch para trainer.py
    # ------------------------------------------------------------------

    def forward(self, state: np.ndarray) -> np.ndarray:
        """
        Ejecuta la red sobre un estado y devuelve la acción como NumPy array.

        Convierte el array de entrada a tensor, invoca PolicyNet.forward(),
        y devuelve el resultado como NumPy. Así, trainer.py no necesita
        importar torch para controlar el vehículo.

        Args:
            state: np.ndarray de shape (14,), dtype float32, con los valores
                   normalizados que devuelve environment.get_state().

        Returns:
            np.ndarray de shape (2,), valores en (0, 1).
            índice 0 = intensidad de aceleración.
            índice 1 = intensidad de frenado.
        """
        # torch.float32 explícito: state puede llegar como float64 (default de
        # np.zeros / np.array) y nn.Linear espera float32.
        tensor_in = torch.tensor(state, dtype=torch.float32)
        tensor_out = self.net(tensor_in)

        # .numpy() comparte memoria con el tensor, pero como PolicyNet usa
        # no_grad(), el tensor no tiene historial y la conversión es segura.
        return tensor_out.numpy()

    # ------------------------------------------------------------------
    # Operadores evolutivos
    # ------------------------------------------------------------------

    def mutate(self) -> None:
        """
        Aplica mutación gaussiana in-place sobre los pesos del genoma.

        Para cada peso w_i, con probabilidad MUTATION_RATE se añade ruido
        gaussiano N(0, MUTATION_SIGMA). Los demás pesos no se tocan.

        Por qué probabilidad por peso (no por genoma):
            Si mutáramos todo el vector o nada, un genoma bueno podría
            destruirse completamente en un solo paso. La granularidad por
            peso permite cambios pequeños y localizados, como las mutaciones
            puntuales en biología.
        """
        weights = self.get_weights()  # copia del vector actual

        # Máscara booleana: True en las posiciones que van a mutar.
        # np.random.rand genera valores uniformes en [0, 1); los menores que
        # MUTATION_RATE forman la máscara de mutación.
        mask = np.random.rand(len(weights)) < MUTATION_RATE

        # Ruido gaussiano de la misma longitud; solo se aplica donde mask=True.
        noise = np.random.randn(len(weights)).astype(np.float32) * MUTATION_SIGMA
        weights[mask] += noise[mask]

        self.set_weights(weights)

    def copy(self) -> "Genome":
        """
        Devuelve una copia profunda del genoma (red + fitness).

        Usado por el elitismo: los mejores individuos pasan a la siguiente
        generación exactamente como están, sin modificación. La copia
        profunda garantiza que mutar al original no afecte al clon ni
        viceversa.

        Returns:
            Nuevo Genome con los mismos pesos y el mismo fitness.
        """
        # copy.deepcopy duplica todos los objetos PyTorch internos de PolicyNet
        # (tensores de parámetros incluidos), produciendo una red completamente
        # independiente en memoria.
        return copy.deepcopy(self)