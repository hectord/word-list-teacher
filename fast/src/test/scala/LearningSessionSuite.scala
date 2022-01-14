import org.scalatest.FunSuite
import learn.vocabulary.{Vocabulary,Word}
import learn.session.Session


class LearningSessionSuite extends FunSuite {

    test("learning session with two words") {
      val first = Word("out1", "in1")
      val second = Word("out2", "in2")
      val voc = new Vocabulary(Set(first, second))
      val session = new Session(voc)
      val firstWord: Option[Word] = session.currentWord

      if(firstWord.filter(_.input == "in2").isDefined)
        session.guess("toto")

      // switch between both words
      assert(Some(first) == session.currentWord)
      session.guess("titi")
      assert(Some(second) == session.currentWord)

      // only one word left
      session.guess(second.output)
      assert(Some(first) == session.currentWord)
      session.guess(second.output)
      assert(Some(first) == session.currentWord)
      session.guess(first.output)
      assert(None == session.currentWord)
    }
}

