$(document).ready(function() {
  var current_word = $("#current-word");
  var current_output = $("#current-output");

  function keep_focus() {
    if (current_output.length && current_word.length &&
        current_word.is(":visible")) {
      current_output.focus();
    }
  }

  keep_focus();

  // on touch devices, keep the keyboard/input focused while practicing
  if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    current_output.on("focusout", function() {
      if (current_word.is(":visible")) {
        setTimeout(keep_focus, 0);
      }
    });
  }

  // click on an example sentence to show/hide its translation in the
  // learner's own language (when available)
  $(".words").on("click", ".word-example.with-input", function () {
    $(this).find(".example-input").toggleClass("hidden");
    $(this).toggleClass("open");
  });

  $("#current-output").keyup(function(e) {

    if($(this).attr('readonly'))
      return;

    if(e.which == 13) {
      var current_input = $("#current-input");
      var output = current_output.val();
      var session_id = current_output.data("session-id");
      var current_word_id = current_output.data("current-word-id");

      $.ajax({
        url: "/word",
        method: "POST",
        contentType: 'application/json',
        processData: false,
        data: JSON.stringify({
          "word": output,
          "session_id": session_id,
          "word_id": current_word_id
        })
      }).done(function(result) {

        if(result.success) {
          var new_node = $("#right-word").clone();
        } else {
          var new_node = $("#wrong-word").clone();
        }

        new_node.attr("style", "");
        new_node.find(".input .field").text(result.word_input.word);
        new_node.find(".output .field").text(result.word_output.word);
        new_node.find(".result .field").text(result.hint);

        // show the example sentence of the practised word (when any),
        // with a click-to-translate version in the learner's language
        var example = new_node.find(".word-example");
        if (result.example || result.input_example) {
          example.attr("style", "");
          if (result.example) {
            example.find(".example-text").text(result.example);
          }
          var translated = result.input_example ? true : false;
          example.toggleClass("with-input", translated);
          example.find(".example-toggle").toggleClass("hidden", !translated);
          // the translation stays hidden until the learner clicks it
          example.find(".example-input")
                 .addClass("hidden")
                 .text(translated ? result.input_example : "");
        } else {
          example.hide();
        }

        // insert the answer right below the pinned current word
        $("#current-word").after(new_node);

        if(result.next_word) {
          current_input.text(result.next_word.word);
          current_output.data("current-word-id", result.next_word.word_id);
          current_output.val("");
        } else {
          $("#current-word").hide();
        }

        keep_focus();
      });
    }
  });

});