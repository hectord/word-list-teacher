package learn.vocabulary

import scala.io.Source


case class InvalidVocabulary(msg: String) extends RuntimeException {}


case class Word(
  input: String,
  output: String,
  directive: Option[String] = None)
{
}


case class Vocabulary(_words: Set[Word] = Set())
{
  def words = _words

  def size = words.size

  def this(iterLine: Iterator[String]) = {
    this(iterLine.flatMap(line => {

      if(line.length == 0) {
        List()
      } else {
        var splitLine = line.split(";")

        if(splitLine.length != 2)
          throw new InvalidVocabulary(s"invalid $line")

        val word_output = splitLine(0)
        val word_input = splitLine(1)

        if(word_output(0) == '#') {
          val (directive, new_word_output) = word_output.span(x => !x.isWhitespace)

          List(new Word(word_input,
                        new_word_output.trim(),
                        Some(directive)))
        } else {
          List(new Word(word_input,
                        word_output))
        }

      }
    }).toSet)
  }

  def this(filename: String) = {
    this(Source.fromFile(filename).getLines)
  }

  def foreach(fonc: (Word => Unit)) {
    words.foreach(fonc)
  }
}
