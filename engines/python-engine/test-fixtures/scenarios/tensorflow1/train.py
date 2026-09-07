import tensorflow as tf

features = tf.placeholder(tf.float32, shape=[None, 4])
with tf.Session() as session:
    session.run(tf.global_variables_initializer())
