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

  // end-of-run statistics (numbers only)
  function summaryElement(summary) {
    if (!summary) { return null; }

    var div = document.createElement("div");
    div.className = "session-summary";
    div.innerHTML =
      "<div class=\"summary-title\">Session summary</div>" +
      "<div class=\"summary-strategy\">strategy: <b>" +
        (summary.strategy === "ai" ? "AI" : "Full") + "</b></div>";

    function appendGrid(title, cells) {
      if (title) {
        var caption = document.createElement("div");
        caption.className = "summary-ai-title";
        caption.textContent = title;
        div.appendChild(caption);
      }
      var grid = document.createElement("div");
      grid.className = "summary-grid";
      var html = "";
      for (var i = 0; i < cells.length; i++) {
        html += "<div class=\"summary-cell\"><span class=\"summary-value\">" +
                cells[i][0] +
                "</span><span class=\"summary-label\">" +
                cells[i][1] +
                "</span></div>";
      }
      grid.innerHTML = html;
      div.appendChild(grid);
    }

    // line one: the regular stats
    appendGrid("", [
      [summary.words_known, "known words"],
      [summary.words_total, "total words"],
      [summary.known_percentage + "%", "known %"],
    ]);

    // line two: only the AI strategy reports per-run progress
    if (summary.new_words !== undefined) {
      appendGrid("AI progress (vs. before this run)", [
        [summary.new_words, "new words"],
        [summary.new_mastered, "new mastered"],
        [summary.new_hard, "new hard"],
      ]);
    }

    // the words to learn again: every word with at least one mistake,
    // the most mistaken first
    var toLearn = summary.words_to_learn || [];
    if (toLearn.length) {
      var list = document.createElement("div");
      list.className = "summary-words";
      var title = document.createElement("div");
      title.className = "summary-words-title";
      title.textContent = "Words to learn (" + toLearn.length + ")";
      list.appendChild(title);
      for (var i = 0; i < toLearn.length; i++) {
        var row = document.createElement("div");
        row.className = "summary-word";
        var word = document.createElement("span");
        word.className = "summary-word-answer";
        word.textContent = toLearn[i].word;
        var input = document.createElement("span");
        input.className = "summary-word-input";
        input.textContent = toLearn[i].input;
        var badge = document.createElement("span");
        badge.className = "summary-word-failures";
        badge.textContent = "\u00d7" + toLearn[i].failures;
        row.appendChild(word);
        row.appendChild(input);
        row.appendChild(badge);
        list.appendChild(row);
      }
      div.appendChild(list);
    }

    return div;
  }

  // a finished session loaded directly still shows its summary
  var embeddedSummary = document.getElementById("session-summary-data");
  if (embeddedSummary) {
    var summary = JSON.parse(embeddedSummary.textContent);
    var node = summaryElement(summary);
    if (node) { embeddedSummary.replaceWith(node); }
  }

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

        // when another correct variant was used, point out which variant
        // this exercise expected, so it is learnt as well
        if (result.used_other_variant) {
          new_node.find(".variant-note")
                  .removeClass("hidden")
                  .find(".variant-used").text(result.word_output.word);
          new_node.find(".variant-note .variant-expected")
                  .text(result.hint);
        }

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
          // the run is over: show the strategy-based statistics as a
          // block at the top of the page
          var node = summaryElement(result.summary);
          if (node) {
            $(".words").prepend(node);
            node.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }

        keep_focus();
      });
    }
  });

});