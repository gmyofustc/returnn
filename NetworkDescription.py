
import inspect
from ActivationFunctions import strtoact
from Util import simpleObjRepr, hdf5_dimension


class LayerNetworkDescription:

  """
  This class is used as a description to build up the LayerNetwork.
  The other options to build up a LayerNetwork are JSON or from a HDF model.
  """

  def __init__(self, num_inputs, num_outputs,
               hidden_info,
               loss, L1_reg, L2_reg, dropout=(),
               bidirectional=True, sharpgates='none',
               truncation=-1, entropy=0):
    """
    :type num_inputs: int
    :type num_outputs: int
    :param list[(str,int,(str,theano.Op)|list[(str,theano.Op)],str)] hidden_info: list of
      (layer_type, size, activation, name)
    :param str loss: loss type, "ce", "ctc" etc
    :type L1_reg: float
    :type L2_reg: float
    :type dropout: list[float]
    :type bidirectional: bool
    :param str sharpgates: see LSTM layers
    :param int truncation: number of steps to use in truncated BPTT or -1. see theano.scan
    :param float entropy: ...
    """
    assert len(dropout) == len(hidden_info) + 1
    self.num_inputs = num_inputs
    self.num_outputs = num_outputs
    self.hidden_info = list(hidden_info)
    self.loss = loss
    self.L1_reg = L1_reg
    self.L2_reg = L2_reg
    self.dropout = list(dropout)
    self.bidirectional = bidirectional
    self.sharpgates = sharpgates
    self.truncation = truncation
    self.entropy = entropy

  def __eq__(self, other):
    return self.init_args() == getattr(other, "init_args", lambda: {})()

  def __ne__(self, other):
    return not self == other

  def init_args(self):
    return {arg: getattr(self, arg) for arg in inspect.getargspec(self.__init__).args[1:]}

  __repr__ = simpleObjRepr

  def copy(self):
    args = self.init_args()
    return self.__class__(**args)

  @classmethod
  def from_config(cls, config):
    """
    :type config: Config.Config
    :returns dict
    """
    num_inputs, num_outputs = cls.num_inputs_outputs_from_config(config)
    loss = cls.loss_from_config(config)
    hidden_size = config.int_list('hidden_size')
    assert len(hidden_size) > 0, "no hidden layers specified"
    hidden_type = config.list('hidden_type')
    assert len(hidden_type) <= len(hidden_size), "too many hidden layer types"
    hidden_name = config.list('hidden_name')
    assert len(hidden_name) <= len(hidden_size), "too many hidden layer names"
    if len(hidden_type) != len(hidden_size):
      n_hidden_type = len(hidden_type)
      for i in xrange(len(hidden_size) - len(hidden_type)):
        if n_hidden_type == 1:
          hidden_type.append(hidden_type[0])
        else:
          hidden_type.append("forward")
    if len(hidden_name) != len(hidden_size):
      for i in xrange(len(hidden_size) - len(hidden_name)):
        hidden_name.append("_")
    for i, name in enumerate(hidden_name):
      if name == "_": hidden_name[i] = "hidden_%d" % i
    L1_reg = config.float('L1_reg', 0.0)
    L2_reg = config.float('L2_reg', 0.0)
    bidirectional = config.bool('bidirectional', True)
    truncation = config.int('truncation', -1)
    actfct = config.list('activation')
    dropout = config.list('dropout', [0.0])
    sharpgates = config.value('sharpgates', 'none')
    entropy = config.float('entropy', 0.0)
    if len(actfct) < len(hidden_size):
      for i in xrange(len(hidden_size) - len(actfct)):
        actfct.append("logistic")
    if len(dropout) < len(hidden_size) + 1:
      for i in xrange(len(hidden_size) + 1 - len(dropout)):
        dropout.append(0.0)
    dropout = [float(d) for d in dropout]
    hidden_info = []; """ :type: list[(str,int,(str,theano.Op)|list[(str,theano.Op)],str)] """
    """
    That represents (layer_type, size, activation, name),
    where activation is either a list of activation functions or a single one.
    Such activation function is a tuple (str,theano.Op).
    name is a custom name for the layer, such as "hidden_2".
    """
    for i in xrange(len(hidden_size)):
      if ':' in actfct[i]:
        acts = []; """ :type: list[(str,theano.Op)] """
        for a in actfct[i].split(':'):
          acts.append((a, strtoact(a)))
      else:
        acts = (actfct[i], strtoact(actfct[i]))
      """
      hidden_name[i]: custom name of the hidden layer, such as "hidden_2"
      hidden_type[i]: e.g. 'forward'
      acts: activation function, e.g. ("tanh", T.tanh)
      """
      hidden_info.append((hidden_type[i], hidden_size[i], acts, hidden_name[i]))

    return cls(num_inputs=num_inputs, num_outputs=num_outputs,
               hidden_info=hidden_info,
               loss=loss, L1_reg=L1_reg, L2_reg=L2_reg, dropout=dropout,
               bidirectional=bidirectional, sharpgates=sharpgates,
               truncation=truncation, entropy=entropy)

  @classmethod
  def loss_from_config(cls, config):
    """
    :type config: Config.Config
    :rtype: str
    """
    return config.value('loss', 'ce')

  @classmethod
  def num_inputs_outputs_from_config(cls, config):
    """
    :type config: Config.Config
    :rtype: (int,int)
    """
    num_inputs = config.int('num_inputs', 0)
    num_outputs = config.int('num_outputs', 0)
    if config.list('train'):
      _num_inputs = hdf5_dimension(config.list('train')[0], 'inputPattSize') * config.int('window', 1)
      _num_outputs = hdf5_dimension(config.list('train')[0], 'numLabels')
      if num_inputs: assert num_inputs == _num_inputs
      if num_outputs: assert num_outputs == _num_outputs
      num_inputs = _num_inputs
      num_outputs = _num_outputs
    assert num_inputs and num_outputs, "provide num_inputs/num_outputs directly or via train"
    loss = cls.loss_from_config(config)
    if loss in ('ctc', 'ce_ctc') or config.bool('add_blank', False):
      num_outputs += 1  # add blank
    return num_inputs, num_outputs