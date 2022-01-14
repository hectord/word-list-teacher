package learn.session

import scala.util.Random
import learn.vocabulary.{Vocabulary, Word}
import scala.collection.mutable.ListBuffer


class Session(voc: Vocabulary)
{
  def swap[A,B](a: A, b: B): (B, A) = (b, a)
  val rnd = new scala.util.Random

  var start = 0
  var end = voc.size
  var wordToLearn: ListBuffer[Word] = { voc.words.to[ListBuffer] }

  def currentWord: Option[Word] = {
    if(start == end)
      None
    else
      Some(wordToLearn(start))
  }

  def sizeLeft = end - start

  def isFinished = currentWord.isEmpty

  def guess(text: String): Boolean = {
    if (wordToLearn(start).output == text) {
      start += 1
      true
    } else {

      if (sizeLeft > 1) {
        val swapPos = start + 1 + rnd.nextInt(end - start - 1)

        var oldWord = wordToLearn(start)

        wordToLearn(start) = wordToLearn(swapPos)
        wordToLearn(swapPos) = oldWord
      }
      false
    }
  }
}
