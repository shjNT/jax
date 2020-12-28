# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests the primitive harness limitations.

Runs all the harnesses surfaces the errors, and detects cases when we have
too many or too few limitations.

"""

import collections
import datetime
import logging
import os
from typing import Dict, Sequence
import unittest

from absl.testing import absltest

from jax import test_util as jtu
from jax.config import config
from jax.experimental.jax2tf.tests import tf_test_util


config.parse_flags_with_absl()
FLAGS = config.FLAGS

# Import after parsing flags
from jax.experimental.jax2tf.tests import primitive_harness


class JaxPrimitiveTest(tf_test_util.JaxToTfTestCase):

  @primitive_harness.parameterized(primitive_harness.all_harnesses,
                                   include_jax_unimpl=True)
  @jtu.ignore_warning(category=UserWarning,
                      message="Using reduced precision for gradient.*")
  def test_jax_implemented(self, harness: primitive_harness.Harness):
    """Runs all harnesses just with JAX to verify the jax_unimplemented field.
    """
    jax_unimpl = [l for l in harness.jax_unimplemented
                  if l.filter(jtu.device_under_test())]
    try:
      harness.dyn_fun(*harness.dyn_args_maker(self.rng()))
    except Exception as e:
      if jax_unimpl:
        logging.info(
          f"Found expected JAX error {e} with expected JAX limitations: "
          f"{[u.description for u in jax_unimpl]} in harness {harness.fullname}")
        return
      else:
        raise e

    if jax_unimpl:
      msg = ("Found no JAX error but expected JAX limitations: "
             f"{[u.description for u in jax_unimpl]} in harness: {harness.fullname}")
      logging.warning(msg)
      # We assert that we don't have too strict limitations. This assert can
      # fail if somebody fixes a JAX or XLA limitation. In that case, you should
      # find and remove the Limitation in primitive_harness. Alternatively,
      # uncomment this assert and ping an OWNER of primitive_harness.
      # self.assertEmpty(msg)

  def test_generate_primitives_coverage_doc(self):
    harnesses = primitive_harness.all_harnesses
    print(f"Found {len(harnesses)} harnesses")

    harness_groups: Dict[str, Sequence[primitive_harness.Harness]] = collections.defaultdict(list)
    unique_limitations = {}

    def unique_hash(l: primitive_harness.Limitation):
      return hash((l.harness.group_name, l.description, l.devices, l.dtypes))

    for h in harnesses:
      harness_groups[h.group_name].append(h)
      for l in h.jax_unimplemented:
        unique_limitations[unique_hash(l)] = l

    primitive_coverage_table = ["""
| Primitive | Total test harnesses | dtypes supported on at least one device | dtypes NOT tested on any device |
| --- | --- | --- | --- | --- |"""]
    all_dtypes = set(jtu.dtypes.all)

    for group_name in sorted(harness_groups.keys()):
      hlist = harness_groups[group_name]
      dtypes_tested = set()  # Tested on at least some device
      for h in hlist:
        dtypes_tested = dtypes_tested.union({h.dtype})

      primitive_coverage_table.append(
        f"| {group_name} | {len(hlist)} | "
        f"{primitive_harness.dtypes_to_str(dtypes_tested)} | "
        f"{primitive_harness.dtypes_to_str(all_dtypes - dtypes_tested)} |")

    print(f"Found {len(unique_limitations)} unique limitations")
    primitive_unimpl_table = ["""
| Affected primitive | Description of limitation | Affected dtypes | Affected devices |
| --- | --- | --- | --- | --- |"""]
    for l in sorted(unique_limitations.values(), key=lambda l: str(l.harness.group_name)):
      devices = ", ".join(l.devices)
      primitive_unimpl_table.append(
        f"|{l.harness.group_name}|{l.description}|"
        f"{primitive_harness.dtypes_to_str(l.dtypes, empty_means_all=True)}|{devices}|")

    if not os.environ.get("JAX_OUTPUT_LIMITATIONS_DOC"):
      raise unittest.SkipTest("Set JAX_OUTPUT_LIMITATIONS_DOC=1 to enable the generation of the documentation")
    # The CPU/GPU have more supported types than TPU.
    self.assertEqual("cpu", jtu.device_under_test(), "The documentation can be generated only on CPU")
    self.assertTrue(FLAGS.jax_enable_x64, "The documentation must be generated with JAX_ENABLE_X64=1")

    with open(os.path.join(os.path.dirname(__file__),
                           '../g3doc/jax_primitives_coverage.md.template')) as f:
      template = f.read()
    output_file = os.path.join(os.path.dirname(__file__),
                               '../g3doc/jax_primitives_coverage.md')

    with open(output_file, "w") as f:
      f.write(template.replace("{{generation_date}}", str(datetime.date.today())) \
              .replace("{{nr_harnesses}}", str(len(harnesses))) \
              .replace("{{nr_primitives}}", str(len(harness_groups))) \
              .replace("{{primitive_unimpl_table}}", "\n".join(primitive_unimpl_table)) \
              .replace("{{primitive_coverage_table}}", "\n".join(primitive_coverage_table)))


if __name__ == "__main__":
  absltest.main(testLoader=jtu.JaxTestLoader())