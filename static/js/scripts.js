// static/js/scripts.js

document.addEventListener('DOMContentLoaded', function() {
    // Función para actualizar el contador del carrito en el navbar
    function updateCartCount() {
        fetch('/api/get_cart_status')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const cartItemCount = document.getElementById('cart-item-count');
                    if (cartItemCount) {
                        cartItemCount.textContent = data.total_items;
                        // Opcional: mostrar/ocultar el badge si el carrito está vacío
                        if (data.total_items > 0) {
                            cartItemCount.classList.remove('d-none');
                        } else {
                            cartItemCount.classList.add('d-none');
                        }
                    }
                }
            })
            .catch(error => console.error('Error fetching cart status:', error));
    }

    // Inicializar el contador al cargar la página
    updateCartCount();

    // Event listener para los botones "Añadir al Carrito"
    document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        button.addEventListener('click', function() {
            const platoId = this.dataset.platoId;
            const quantity = 1; // Por defecto se añade 1 unidad

            fetch(`/api/add_to_cart/${platoId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: `cantidad=${quantity}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // alert(data.message); // Podrías usar un toast o un mensaje más amigable
                    updateCartCount();
                    // Opcional: mostrar un feedback visual de que se añadió
                    this.textContent = '¡Añadido!';
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-success');
                    setTimeout(() => {
                        this.innerHTML = '<i class="bi bi-cart-plus"></i> Añadir al Carrito';
                        this.classList.remove('btn-success');
                        this.classList.add('btn-primary');
                    }, 1500);
                } else {
                    alert('Error al añadir al carrito: ' + data.message);
                }
            })
            .catch(error => console.error('Error:', error));
        });
    });

    // Nueva ruta para limpiar todo el carrito
    document.addEventListener('DOMContentLoaded', function() {
        // ... (código existente del carrito en hacer_pedido.html si lo moviste aquí) ...

        const clearCartBtn = document.getElementById('clear-cart-btn');
        if (clearCartBtn) {
            clearCartBtn.addEventListener('click', function() {
                if (confirm('¿Estás seguro de que quieres vaciar todo el carrito?')) {
                    fetch('/api/clear_cart', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert(data.message);
                            window.location.reload();
                        } else {
                            alert('Error al vaciar carrito: ' + data.message);
                        }
                    })
                    .catch(error => console.error('Error:', error));
                }
            });
        }
    });
});

// Nueva ruta de API para limpiar el carrito (añadir esto en app.py)
/*
@app.route('/api/clear_cart', methods=['POST'])
def clear_cart():
    session.pop('carrito', None)
    session.modified = True
    return jsonify({"success": True, "message": "Carrito vaciado."})
*/