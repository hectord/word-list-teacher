// Vocabulary filtering for the /index page: type in the search box to
// narrow the vocabulary list (the same behaviour as the word filter on
// the vocabulary page).
$(function () {
  var $input = $("#voc-filter");
  var $count = $("#voc-filter-count");
  var $cards = $(".vocabulary[data-search]");
  var $empty = $(".no-voc-match");

  if (!$input.length) {
    return;
  }

  function apply() {
    var query = $input.val().toLowerCase().trim();
    var visible = 0;

    $cards.each(function () {
      var $card = $(this);
      var matches = !query ||
        ($card.data("search") || "").indexOf(query) !== -1;
      $card.toggle(matches);
      if (matches) {
        visible++;
      }
    });

    $count.text(query ? visible + " / " + $cards.length + " shown" : "");
    $empty.prop("hidden", !(query && visible === 0));
  }

  $input.on("input", apply);
  apply();
});
