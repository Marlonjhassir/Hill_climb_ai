"""
ai/neural_network.py — Red neuronal de política para neuroevolución.

Responsabilidades:
  - Implementar PolicyNet: 14 → 16 (tanh) → 12 (tanh) → 2 (sigmoid).
  - Exponer get_weights() / set_weights() para que genome.py manipule los
    pesos como vectores 1D de NumPy (interfaz del algoritmo genético).

Prohibido: usar optimizer, loss.backward(), o cualquier mecanismo de autograd.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.nn.utils import parameters_to_vector, vector_to_parameters

from config.settings import NN_INPUTS, NN_HIDDEN, NN_OUTPUTS


class PolicyNet(nn.Module):
    """
    Red neuronal de política para el vehículo Hill Climb.

    Arquitectura: 14 → 16 (tanh) → 12 (tanh) → 2 (sigmoid).

    'Policy' porque mapea un estado observado del entorno (14 valores
    normalizados) a una acción (intensidad de aceleración e intensidad
    de frenado, ambas en [0, 1]).

    No usa backpropagation. Los pesos se optimizan mediante neuroevolución:
    el algoritmo genético los trata como un vector 1D y aplica crossover
    y mutación directamente sobre los números.

    Args:
        n_in:   número de entradas (default: NN_INPUTS = 14).
        hidden: lista de tamaños de capas ocultas (default: NN_HIDDEN = [16, 12]).
        n_out:  número de salidas (default: NN_OUTPUTS = 2).

    Example:
        >>> net = PolicyNet()
        >>> state = torch.zeros(14)
        >>> action = net(state)  # tensor de shape (2,), valores en (0, 1)
    """

    def __init__(
        self,
        n_in:   int       = NN_INPUTS,
        hidden: list[int] = NN_HIDDEN,
        n_out:  int       = NN_OUTPUTS,
    ) -> None:
        super().__init__()

        # Construir capas dinámicamente para que la arquitectura sea configurable
        # desde settings.py sin modificar este archivo.
        layers: list[nn.Module] = []
        prev = n_in

        # Capas ocultas: cada una es Linear + Tanh.
        # Tanh es preferida a ReLU en neuroevolución porque siempre produce
        # salida no nula (rango (-1, 1)), lo que mantiene la red "activa"
        # incluso cuando los pesos son aleatorios o están en zonas planas.
        for h in hidden:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.Tanh())
            prev = h

        # Capa de salida: Linear + Sigmoid.
        # Sigmoid garantiza que aceleración y frenado estén en [0, 1],
        # que es exactamente el rango semántico de "intensidad de control".
        layers.append(nn.Linear(prev, n_out))
        layers.append(nn.Sigmoid())

        self.net = nn.Sequential(*layers)

        # Desactivar gradientes en TODOS los parámetros.
        # En neuroevolución no usamos backprop: el fitness es una caja negra
        # (resultado de un episodio completo) y no es diferenciable.
        # requires_grad=False ahorra memoria y hace imposible un .backward()
        # accidental que corrompería la lógica evolutiva.
        for param in self.parameters():
            param.requires_grad = False

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Ejecuta la red sobre un estado de entrada.

        El contexto no_grad refuerza la prohibición de autograd aunque alguien
        llame a forward() desde fuera de genome.py sin precaución.

        Args:
            x: tensor de shape (n_in,) para un único estado, o (batch, n_in)
               para un lote. En el uso normal del juego será (14,).

        Returns:
            Tensor de shape (n_out,) o (batch, n_out), con valores en (0, 1).
            salida[0] = intensidad de aceleración.
            salida[1] = intensidad de frenado.
        """
        # torch.no_grad() evita que PyTorch construya el grafo computacional.
        # Resultado: ~30% menos de memoria y mayor velocidad en el forward.
        with torch.no_grad():
            return self.net(x)

    # ------------------------------------------------------------------
    # Serialización de pesos (interfaz para genome.py)
    # ------------------------------------------------------------------

    def get_weights(self) -> np.ndarray:
        """
        Extrae todos los parámetros como un vector 1D NumPy float32.

        El vector concatena, en orden de registro: W_capa1, b_capa1,
        W_capa2, b_capa2, W_salida, b_salida.

        Para nuestra arquitectura 14→16→12→2:
          - Linear(14,16): 224 pesos + 16 sesgos = 240
          - Linear(16,12): 192 pesos + 12 sesgos = 204
          - Linear(12, 2):  24 pesos +  2 sesgos =  26
          - Total: 470 parámetros.

        Returns:
            np.ndarray de shape (n_params,) y dtype float32. Es una COPIA:
            modificar el array no afecta los pesos de la red.
        """
        # parameters_to_vector concatena todos los tensores de parámetros en uno.
        # .detach() elimina cualquier historial de gradiente (aunque ya es False).
        # .numpy() comparte memoria con el tensor; .copy() garantiza una copia
        # independiente para que genome.py pueda mutar el array sin efectos secundarios.
        return parameters_to_vector(self.parameters()).detach().numpy().copy()

    def set_weights(self, weights: np.ndarray) -> None:
        """
        Inyecta un vector 1D NumPy en los parámetros de la red (in-place).

        Args:
            weights: np.ndarray de shape (n_params,) y dtype float32.
                     Debe tener exactamente self.n_params elementos.

        Raises:
            ValueError: si el tamaño del vector no coincide con n_params.
        """
        if weights.shape[0] != self.n_params:
            raise ValueError(
                f"Se esperaban {self.n_params} parámetros, "
                f"se recibieron {weights.shape[0]}."
            )
        # Convertir el array NumPy a tensor PyTorch antes de inyectarlo.
        # torch.float32 explícito para evitar conflictos de dtype si el array
        # llega como float64 (el default de NumPy para np.random.randn).
        vector = torch.tensor(weights, dtype=torch.float32)
        vector_to_parameters(vector, self.parameters())

    # ------------------------------------------------------------------
    # Propiedad de utilidad
    # ------------------------------------------------------------------

    @property
    def n_params(self) -> int:
        """
        Número total de parámetros escalares (pesos + sesgos de todas las capas).

        Útil para que genome.py inicialice vectores del tamaño correcto sin
        tener que instanciar una red primero.
        """
        # sum(p.numel() for p in ...) cuenta todos los escalares de cada tensor.
        return sum(p.numel() for p in self.parameters())