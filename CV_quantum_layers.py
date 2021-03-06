# %% Imports
import tensorflow as tf
from tensorflow import keras
import pennylane as qml
import numpy as np
#%% CV Data Encoding
"""These functions described different options for encoding
PennyLane provides Displacement for amplitude OR phase, and Squeezing."""

def AmplitudePhaseDisplacementEncoding(features, wires):
    """Encode N data points in N/2 qumodes where pairs of features are
    encoded as amplitudes and phases of the displacement gate.
    Later, this should be modified to alter each pair to be complex valued,
    and then converted to angle and phase to put the data points on equal footing.
    Assumes ordering of (displacement, angle, displacement, angle, ...)"""
    for idx, f in enumerate(features):
        if(idx%2==0):
            qml.Displacement(f, features[idx+1], wires=wires[int(idx/2)])

#%% CV Quantum Nodes
"""Builds a quantum node based on the specifications"""

def build_cv_quantum_node(n_qumodes, n_outputs, cutoff_dim, encoding_method, meas_method="X_quadrature"):
    dev = qml.device("strawberryfields.tf", wires=n_qumodes, cutoff_dim=cutoff_dim)
    @qml.qnode(dev, interface="tf")
    def cv_nn(inputs, theta_1, phi_1, varphi_1, r, phi_r, theta_2, phi_2, varphi_2, a, phi_a, k):
        encoding_method(inputs, wires=range(n_qumodes))
        qml.templates.CVNeuralNetLayers(theta_1,
                                        phi_1,
                                        varphi_1,
                                        r,
                                        phi_r,
                                        theta_2,
                                        phi_2,
                                        varphi_2,
                                        a,
                                        phi_a,
                                        k,
                                        wires=range(n_qumodes))
        if(meas_method=="X_quadrature"):
            return [qml.expval(qml.X(wires=i)) for i in range(n_outputs)]
        elif(meas_method=="Fock"):
            return [qml.probs(wires=i) for i in range(n_outputs)]
        else:
            print("Please enter valid measurement type")

    return cv_nn

#%% Custom regularizer for loss method
class Norm(tf.keras.regularizers.Regularizer):
    def __init__(self, l=0.1):
        self.norm = tf.keras.backend.variable(1.0, name='norm')
        self.val_norm = 1.0
        self.l = l

    def set_norm(self, norm):
        tf.keras.backend.set_value(self.norm, norm)
        self.val_norm = norm

    def __call__(self, x):
        return self.l * tf.reduce_sum(((1-self.norm) ** 2) * tf.abs(x))

    def get_config(self):
        config = {'norm': float(tf.keras.backend.get_value(self.norm)),
                  'l': float(self.l)}
        return config
    
#%% Single CV Keras Layer
"""Builds a Keras Layer using a quantum node"""

def build_cv_neural_network(n_qumodes, n_outputs, n_layers, cutoff_dim, encoding_method, regularizer, input_amplitude, meas_method="X_quadrature"):

    # Make quantum node
    cv_nn = build_cv_quantum_node(n_qumodes, n_outputs, cutoff_dim, encoding_method, meas_method)

    # Define weight shapes
    L = n_layers
    M = n_qumodes
    K = int(M * (M - 1) / 2)
    weight_shapes = {"theta_1":     (L, K),
                     "phi_1":       (L, K),
                     "varphi_1":    (L, M),
                     "r":           (L, M),
                     "phi_r":       (L, M),
                     "theta_2":     (L, K),
                     "phi_2":       (L, K),
                     "varphi_2":    (L, M),
                     "a":           (L, M),
                     "phi_a":       (L, M),
                     "k":           (L, M)
                     }

    # Hardcoded seed for phases for consistency between trials
    seed = 16

    circuit = qml.qnn.KerasLayer(cv_nn, weight_shapes, output_dim=n_outputs, weight_specs={
        "theta_1": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "phi_1": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "varphi_1": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},

        "r": {"initializer": tf.keras.initializers.Constant(input_amplitude), "regularizer": regularizer},

        "phi_r": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "theta_2": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "phi_2": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "varphi_2": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},

        "a": {"initializer": tf.keras.initializers.Constant(input_amplitude), "regularizer": regularizer},

        "phi_a": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))},
        "k": {"initializer": tf.random_uniform_initializer(minval=0, maxval=2*np.pi, seed=tf.random.set_seed(seed))}
    })

    return circuit

#%% Full CV Keras Layers
class QuantumLayer(keras.Model):
    """ This class builds a quantum layer that can be directly used in model building.
    Note that while it is not strictly necessary for this case, it will be expanding upon
    to build more complex layers later on. """
    def __init__(self, n_qumodes, n_outputs, n_layers, cutoff_dim, encoding_method, cutoff_management, cutoff_management_coefficient, input_amplitude):
        super().__init__()
        self.n_outputs = n_outputs

        # Create regularizer
        if cutoff_management == "L1":
            self.regularizer = tf.keras.regularizers.L1(l1=cutoff_management_coefficient)
        elif cutoff_management == "L2":
            self.regularizer = tf.keras.regularizers.L2(l2=cutoff_management_coefficient)
        elif cutoff_management == "Loss":
            self.regularizer = Norm(l=cutoff_management_coefficient)
        else:
            self.regularizer = None
        
        self.circuit_layer = build_cv_neural_network(n_qumodes, n_outputs, n_layers, cutoff_dim, encoding_method, self.regularizer, input_amplitude, meas_method = "X_quadrature")
        self.normalization_qnode= build_cv_quantum_node(n_qumodes, n_outputs, cutoff_dim, encoding_method, meas_method = "Fock")
        self.cutoff_management = cutoff_management
        self.cutoff_management_coefficient = cutoff_management_coefficient

    def call(self, x):
        output = self.circuit_layer(x)

        # Get normalization
        net_norm = 0
        weights = tuple(self.trainable_weights)
        for sample in x:
            fock_dist = self.normalization_qnode(sample, *weights)
            net_norm += np.sum(tf.math.real(fock_dist)) / self.n_outputs
        net_norm = net_norm/len(x)
        self.add_metric(net_norm, "net_norm")

        if(self.cutoff_management=="Loss"): 
            self.regularizer.set_norm(net_norm)

        return output

    def check_normalization(self, x):
        """Currently only accepts single inputs"""
        weights = tuple(self.trainable_weights)
        fock_dist = self.normalization_qnode(x, *weights)
        integral = np.sum(fock_dist)/self.n_outputs
        return integral


# %% Full CV Keras Layers
class QuantumLayer_MultiQunode(keras.Model):
    """ This class builds a quantum layer that can be directly used in model building.
    Note that while it is not strictly necessary for this case, it will be expanding upon
    to build more complex layers later on. """

    def __init__(self, n_inputs, n_outputs, n_circuits, n_qumodes, n_layers, cutoff_dim, encoding_method, cutoff_management,
                 cutoff_management_coefficient, input_amplitude):
        super().__init__()
        self.n_inputs = n_inputs
        self.n_outputs = n_outputs
        self.n_circuits = n_circuits

        # Create regularizer
        if cutoff_management == "L1":
            self.regularizer = tf.keras.regularizers.L1(l1=10000)
        elif cutoff_management == "L2":
            self.regularizer = tf.keras.regularizers.L2(l2=cutoff_management_coefficient)
        elif cutoff_management == "Loss":
            self.regularizer = Norm(l=cutoff_management_coefficient)
        else:
            self.regularizer = None

        self.cutoff_management = cutoff_management
        self.cutoff_management_coefficient = cutoff_management_coefficient

        self.normalization_qnode = build_cv_quantum_node(n_qumodes, n_outputs, cutoff_dim, encoding_method,
                                                         meas_method="Fock")

        self.circuit_layer = [build_cv_neural_network(n_qumodes, n_outputs, n_layers, cutoff_dim, encoding_method,
                                                     self.regularizer, input_amplitude, meas_method="X_quadrature")
                              for i in range(self.n_circuits)]

        self.normalization_qnode = [build_cv_quantum_node(n_qumodes, n_outputs, cutoff_dim, encoding_method,
                                                         meas_method="Fock")
                              for i in range(self.n_circuits)]

    def call(self, x):
        x_split = list(tf.split(x, self.n_circuits, axis=1))
        output = tf.concat([self.circuit_layer[i](x_split[i]) for i in range(self.n_circuits)], axis=1)

        # Get normalization
        net_norm = 0
        for i in range(self.n_circuits):
            x = x_split[i]
            weights = tuple(self.trainable_weights) # Need to change this to get weight of current block
            for sample in x:
                fock_dist = self.normalization_qnode[i](sample, *weights)
                net_norm += np.sum(tf.math.real(fock_dist)) / self.n_outputs
        net_norm = net_norm / len(x)
        self.add_metric(net_norm, "net_norm")

        if (self.cutoff_management == "Loss"):
            self.regularizer.set_norm(net_norm)

        return output
