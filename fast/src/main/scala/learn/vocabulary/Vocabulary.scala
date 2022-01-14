package learn.vocabulary

import scala.io.Source


case class InvalidVocabulary(msg: String) extends RuntimeException {}


case class Word(
  input: String,
  output: String,
  directive: Option[String] = None)
{
  private def filter(value: String): (String, Option[String]) = {
    val stringWithHint = raw"([^\(]*)\((.*)\)".r

    value match {
      case stringWithHint(string, hint) => (string.strip, Some(hint))
      case string => (string, None)
    }
  }

  def accepts(output: String): Boolean = {
    output.filter(_ != '|').toLowerCase() == wordOutput
  }

  def wordInput: String = filter(input)._1
  def wordOutput: String = filter(output)._1
  def hintInput: Option[String] = filter(input)._2
  def hintOutput: Option[String] = filter(output)._2
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

        val wordOutput = splitLine(0)
        val wordInput = splitLine(1)

        if(wordOutput(0) == '#') {
          val (directive, newWordOutput) = wordOutput.span(x => !x.isWhitespace)

          List(new Word(wordInput,
                        newWordOutput.trim(),
                        Some(directive)))
        } else {
          List(new Word(wordInput,
                        wordOutput))
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
