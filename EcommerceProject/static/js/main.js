// Vanilla JS enhancements — no framework needed for a few small UX touches.

document.addEventListener('DOMContentLoaded', function () {
    // Quantity stepper buttons (used on cart page and product detail page)
    document.querySelectorAll('.qty-stepper').forEach(function (stepper) {
        var input = stepper.querySelector('input[type="number"]');
        var minus = stepper.querySelector('.qty-minus');
        var plus = stepper.querySelector('.qty-plus');
        if (!input) return;

        if (minus) {
            minus.addEventListener('click', function () {
                var val = parseInt(input.value || '1', 10);
                if (val > 1) input.value = val - 1;
            });
        }
        if (plus) {
            plus.addEventListener('click', function () {
                var max = parseInt(input.getAttribute('max') || '9999', 10);
                var val = parseInt(input.value || '1', 10);
                if (val < max) input.value = val + 1;
            });
        }
    });

    // Confirm before destructive actions (cancel order, delete address, etc.)
    document.querySelectorAll('.confirm-action').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            var msg = form.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(msg)) {
                e.preventDefault();
            }
        });
    });
});
