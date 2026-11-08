import sys
import unittest

sys.dont_write_bytecode = True

from tools import gen_cx1_go_vectors


class GoVectorFile(unittest.TestCase):
    def test_go_vector_file_matches_python_policy(self):
        current = gen_cx1_go_vectors.TARGET.read_text(encoding="utf-8")
        self.assertEqual(current, gen_cx1_go_vectors.render(),
                         "run python -I -B tools/gen_cx1_go_vectors.py and commit the Go file")


if __name__ == "__main__":
    unittest.main()
