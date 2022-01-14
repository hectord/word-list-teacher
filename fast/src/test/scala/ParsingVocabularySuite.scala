import org.scalatest.FunSuite
import learn.vocabulary.{Vocabulary,Word}


class ParsingVocabularySuite extends FunSuite {

    test("parsing vocabulary") {
      val voc = new Vocabulary(Iterator("out1;in1", "out2;in2"))

      assert(voc.words == Set(Word("in1", "out1"),
                              Word("in2", "out2")))
    }

    test("parsing directive") {
      val voc = new Vocabulary(Iterator("#name out1;in1"))

      assert(voc.words == Set(Word("in1", "out1", Some("#name"))))
    }
}
