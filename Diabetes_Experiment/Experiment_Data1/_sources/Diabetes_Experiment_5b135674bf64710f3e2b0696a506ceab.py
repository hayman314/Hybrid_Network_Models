# TensorFlow
import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, Callback
from tensorflow.keras.losses import categorical_crossentropy
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras import activations

# NumPy
import numpy as np

# Custom Quantum Layers
from CV_quantum_layers import *

# Sacred Package for Experiment Management
from sacred import Experiment
from sacred.observers import FileStorageObserver
from sacred.utils import apply_backspaces_and_linefeeds


# Other
import time
import itertools
import os

# Load pre-processed dataset
from Diabetes_dataset import data_ingredient, load_data

#%% Setup Experiment
ex = Experiment('Diabetes', ingredients=[data_ingredient])
ex.observers.append(FileStorageObserver('Experiment_Data1'))
ex.captured_out_filter = apply_backspaces_and_linefeeds

#%% Experiment Parameters
@ex.config
def confnet_config():
    encoding_strategy = "None"
    cutoff_dimension = 30

#%% Logs
@ex.capture
def log_performance(_run, logs, epoch, time, norm):
    _run.log_scalar("loss", float(logs.get('loss')), epoch)
    _run.log_scalar("accuracy", float(logs.get('accuracy')), epoch)
    _run.log_scalar("val_loss", float(logs.get('val_loss')), epoch)
    _run.log_scalar("val_accuracy", float(logs.get('val_accuracy')), epoch)
    _run.log_scalar("normalization", float(norm), epoch)
    _run.log_scalar("epoch", int(epoch), epoch)
    _run.log_scalar("time", float(time), epoch)

#%% Main
@ex.automain
def define_and_train(encoding_strategy, cutoff_dimension):

    # Fixed parameters
    batch_size = 20
    learning_rate = 0.01
    loss_coefficient = 0.01
    cutoff_management = "L2"
    num_epochs = 50
    seed = 12

    # Metric Logging Callback
    class LogPerformance(Callback):
        def __init__(self):
            super(LogPerformance, self).__init__()

        def on_epoch_begin(self, epoch, logs={}):
            self.start_time = time.time()

        def on_epoch_end(self, epoch, logs={}):
            indexes = np.random.randint(10, size=3)
            samples = tf.concat([[x_train[indexes[i], :]] for i in range(3)], 0)
            net_norm = model.quantum_layer.check_normalization(samples)

            stop_time = time.time()
            duration = stop_time - self.start_time
            log_performance(logs=logs, epoch=epoch, time=duration, norm=net_norm)

    # Load dataset
    x_train, y_train, x_test, y_test = load_data()

    # Define model
    class Net(tf.keras.Model):
        def __init__(self):
            super(Net, self).__init__()

            self.sequential_1 = tf.keras.Sequential([
                layers.Dense(8, activation="relu",
                             kernel_initializer=tf.keras.initializers.GlorotUniform(seed=tf.random.set_seed(seed)),
                             bias_initializer='zeros')])

            self.quantum_layer = QuantumLayer_MultiQunode(8, 4, 2, 2, 1, cutoff_dimension, AmplitudePhaseDisplacementEncoding,
                                         cutoff_management, loss_coefficient)

            self.sequential_2 = tf.keras.Sequential([
                self.quantum_layer,
                layers.Dense(8, activation="relu",
                             kernel_initializer=tf.keras.initializers.GlorotUniform(seed=tf.random.set_seed(seed)),
                             bias_initializer='zeros'),
                layers.Dense(2, activation="sigmoid",
                             kernel_initializer=tf.keras.initializers.GlorotUniform(seed=tf.random.set_seed(seed)),
                             bias_initializer='zeros')])

            self.normalization = layers.BatchNormalization()

        def call(self, inputs):
            x = self.sequential_1(inputs)

            if (encoding_strategy == "Sigmoid_BatchNorm"):
                x = self.normalization(x)
                x = activations.sigmoid(x)

            if(encoding_strategy=="Sigmoid"):
                x = activations.sigmoid(x)

            x = self.sequential_2(x)
            return x

    # Compile model
    model = Net()
    model.compile(loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=False),
                  optimizer=tf.keras.optimizers.Adam(learning_rate),
                  metrics=['accuracy']
                  )

    # Train model
    model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=num_epochs,
                  initial_epoch=0,
                  verbose=1,
                  validation_data=(x_test, y_test),
                  callbacks=[LogPerformance()]
                  )

