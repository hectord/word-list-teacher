// Client-side word filter for the /vocabulary page.
$(function () {
  var $rows = $("#word-list .row[data-search]");
  var $count = $("#filter-count");

  $("#word-filter").on("input", function () {
    var q = this.value.toLowerCase().trim();
    var visible = 0;

    $rows.each(function () {
      var show = $(this).data("search").indexOf(q) !== -1;
      $(this).toggle(show);
      if (show) { visible++; }
    });

    if ($count.length) {
      $count.text(visible + " / " + $rows.length + " shown");
    }
  });
});