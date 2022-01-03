
function update_height() {
  var size = $(".words").height() + 100;
  $(".centering-box").css("top", "calc(100% - " + size + "px)");
}

$(document).ready(function() {
  update_height();

  $("#current-output").keyup(function(e) {

    if($(this).attr('readonly'))
      return;

    if(e.which == 13) {
      var current_input = $("#current-input");
      var current_output = $("#current-output");
      var output = current_output.val();
      var session_id = $("#current-output").data("session-id");

      $.ajax({
        url: "/word",
        method: "POST",
        contentType: 'application/json',
        processData: false,
        data: JSON.stringify({
          "word": output,
          "session_id": session_id
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

        $(".current").before(new_node);

        if(result.next_word) {
          current_input.text(result.next_word.word)
          current_output.val("");
        } else {
          $("#current-word").hide();
        }

        // update the size of the words
        update_height();
      });
    }
  });

});
