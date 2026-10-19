use std::process::ExitCode;

use an3_rust_gateway::{app, AppState, GatewayConfig};
use tokio::net::TcpListener;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with_target(false)
        .compact()
        .init();

    let config = match GatewayConfig::from_env() {
        Ok(config) => config,
        Err(message) => {
            error!("configuration error: {message}");
            return ExitCode::from(2);
        }
    };
    let bind_addr = config.bind_addr;
    let state = AppState::new(config).await;
    let listener = match TcpListener::bind(bind_addr).await {
        Ok(listener) => listener,
        Err(error) => {
            error!("could not bind gateway listener: {error}");
            return ExitCode::from(1);
        }
    };

    info!(address = %bind_addr, "AN3 Rust shadow gateway listening");
    let server = axum::serve(listener, app(state)).with_graceful_shutdown(shutdown_signal());
    if let Err(error) = server.await {
        error!("gateway server failed: {error}");
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C signal handler");
    };

    #[cfg(unix)]
    {
        let terminate = async {
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("failed to install SIGTERM signal handler")
                .recv()
                .await;
        };
        tokio::select! {
            _ = ctrl_c => {},
            _ = terminate => {},
        }
    }

    #[cfg(not(unix))]
    ctrl_c.await;
}
