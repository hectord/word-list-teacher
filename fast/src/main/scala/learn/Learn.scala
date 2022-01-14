package learn

import java.io.{FileNotFoundException, IOException}
import learn.vocabulary.{Vocabulary, Word}
import learn.session.Session
import scala.io.StdIn


object Main extends App
{
  try {
    var voc = new Vocabulary("../vocabulary/test2.txt")
    var session = new Session(voc)

    voc.foreach(println)

    while(!session.isFinished) {
      session.currentWord match {
        case Some(word) => {
          println()
          println(word.input)
          print("# ")
          if(session.guess(StdIn.readLine())) {
            println("Success")
          } else {
            println(s"Error, ${word.output}")
          }
        }
        case None =>
      }
    }
  } catch {
    case e: FileNotFoundException => println("not found")
    case e: IOException => println("IOException")
  }
}
