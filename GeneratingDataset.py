
from Dataset import Dataset, DatasetSeq
from random import randint
from random import random as rnd01
import random
from Util import class_idx_seq_to_features
import numpy


class GeneratingDataset(Dataset):

  def __init__(self, input_dim, output_dim, window=1, num_seqs=float("inf"), *args, **kwargs):
    assert window == 1
    super(GeneratingDataset, self).__init__(window, *args, **kwargs)
    assert self.shuffle_frames_of_nseqs == 0

    self.num_inputs = input_dim
    self.num_outputs = output_dim
    self._num_seqs = num_seqs

  def init_seq_order(self, epoch=None):
    """
    :type epoch: int|None
    This is called when we start a new epoch, or at initialization.
    """
    super(GeneratingDataset, self).init_seq_order(epoch=epoch)
    self._num_timesteps = 0
    self.reached_final_seq = False
    self.expected_load_seq_start = 0
    self.added_data = []; " :type: list[DatasetSeq] "

  def _cleanup_old_seqs(self, seq_idx_end):
    i = 0
    while i < len(self.added_data):
      if self.added_data[i].seq_idx >= seq_idx_end:
        break
      i += 1
    del self.added_data[:i]

  def _get_seq(self, seq_idx):
    for data in self.added_data:
      if data.seq_idx == seq_idx:
        return data
    return None

  def is_cached(self, start, end):
    # Always False, to force that we call self._load_seqs().
    # This is important for our buffer management.
    return False

  def _load_seqs(self, start, end):
    """
    :param int start: inclusive seq idx start
    :param int end: exclusive seq idx end
    """
    # We expect that start increase monotonic on each call
    # for not-yet-loaded data.
    # This will already be called with _load_seqs_superset indices.
    assert start >= self.expected_load_seq_start
    if start > self.expected_load_seq_start:
      # Cleanup old data.
      self._cleanup_old_seqs(start)
      self.expected_load_seq_start = start
    if self.added_data:
      start = max(self.added_data[-1].seq_idx + 1, start)
    if end > self.num_seqs:
      end = self.num_seqs
    if end >= self.num_seqs:
      self.reached_final_seq = True
    seqs = [self.generate_seq(seq_idx=seq_idx) for seq_idx in range(start, end)]
    self._num_timesteps += sum([seq.num_frames for seq in seqs])
    self.added_data += seqs

  def generate_seq(self, seq_idx):
    """
    :type seq_idx: int
    :rtype: DatasetSeq
    """
    raise NotImplementedError

  def _shuffle_frames_in_seqs(self, start, end):
    assert False, "Shuffling in GeneratingDataset does not make sense."

  def get_num_timesteps(self):
    assert self.reached_final_seq
    return self._num_timesteps

  @property
  def num_seqs(self):
    return self._num_seqs

  def get_seq_length(self, sorted_seq_idx):
    # get_seq_length() can be called before the seq is loaded via load_seqs().
    # Thus, we just call load_seqs() ourselves here.
    assert sorted_seq_idx >= self.expected_load_seq_start
    self.load_seqs(self.expected_load_seq_start, sorted_seq_idx + 1)
    return self._get_seq(sorted_seq_idx).num_frames

  def get_data(self, sorted_seq_idx):
    return self._get_seq(sorted_seq_idx).features

  def get_targets(self, sorted_seq_idx):
    return self._get_seq(sorted_seq_idx).targets

  def get_ctc_targets(self, sorted_seq_idx):
    assert self._get_seq(sorted_seq_idx).ctc_targets


class Task12AXDataset(GeneratingDataset):
  """
  12AX memory task.
  This is a simple memory task where there is an outer loop and an inner loop.
  Description here: http://psych.colorado.edu/~oreilly/pubs-abstr.html#OReillyFrank06
  """

  _input_classes = "123ABCXYZ"
  _output_classes = "LR"

  def __init__(self, **kwargs):
    super(Task12AXDataset, self).__init__(
      input_dim=len(self._input_classes),
      output_dim=len(self._output_classes),
      **kwargs)

  @classmethod
  def get_random_seq_len(cls):
    return randint(10, 100)

  @classmethod
  def generate_input_seq(cls, seq_len):
    """
    Somewhat made up probability distribution.
    Try to make in a way that at least some "R" will occur in the output seq.
    Otherwise, "R"s are really rare.
    """
    seq = random.choice(["", "1", "2"])
    while len(seq) < seq_len:
      if rnd01() < 0.5:
        seq += random.choice("12")
      if rnd01() < 0.9:
        seq += random.choice(["AX", "BY"])
      while rnd01() < 0.5:
        seq += random.choice(cls._input_classes)
    return list(map(cls._input_classes.index, seq[:seq_len]))

  @classmethod
  def make_output_seq(cls, input_seq):
    """
    :type input_seq: list[int]
    :rtype: list[int]
    """
    outer_state = ""
    inner_state = ""
    input_classes = cls._input_classes
    output_seq_str = ""
    for i in input_seq:
      c = input_classes[i]
      o = "L"
      if c in "12":
        outer_state = c
      elif c in "AB":
        inner_state = c
      elif c in "XY":
        if outer_state + inner_state + c in ["1AX", "2BY"]:
          o = "R"
        inner_state = ""
      # Ignore other cases, "3CZ".
      output_seq_str += o
    return list(map(cls._output_classes.index, output_seq_str))

  @classmethod
  def estimate_output_class_priors(cls, num_trials, seq_len=10):
    """
    :type num_trials: int
    :rtype: (float, float)
    """
    count_l, count_r = 0, 0
    for i in range(num_trials):
      input_seq = cls.generate_input_seq(seq_len)
      output_seq = cls.make_output_seq(input_seq)
      count_l += output_seq.count(0)
      count_r += output_seq.count(1)
    return float(count_l) / (num_trials * seq_len), float(count_r) / (num_trials * seq_len)

  @classmethod
  def generate_seq(cls, seq_idx):
    seq_len = cls.get_random_seq_len()
    input_seq = cls.generate_input_seq(seq_len)
    output_seq = cls.make_output_seq(input_seq)
    features = class_idx_seq_to_features(input_seq, num_classes=len(cls._input_classes))
    targets = numpy.array(output_seq)
    return DatasetSeq(seq_idx=seq_idx, features=features, targets=targets)