import org.scalatest.FunSuite
import learn.vocabulary.{Vocabulary,Word}


class ParsingVocabularySuite extends FunSuite {

    test("hint in string") {
      val w = Word("in1 (ok)", "out1 (ko)")
      assert(w.wordInput == "in1")
      assert(w.wordOutput == "out1")

      assert(w.hintInput == Some("ok"))
      assert(w.hintOutput == Some("ko"))
      assert(w.accepts("out1"))
      assert(w.accepts("O|Ut1"))
    }

    test("parsing vocabulary") {
      val voc = new Vocabulary(Iterator("out1 (ok);in1", "out2;in2"))

      assert(voc.words == Set(Word("in1", "out1 (ok)"),
                              Word("in2", "out2")))
    }

    test("parsing directive") {
      val voc = new Vocabulary(Iterator("#name out1;in1"))

      assert(voc.words == Set(Word("in1", "out1", Some("#name"))))
    }

}
