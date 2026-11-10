import Nav from "../components/Nav";
import Providers from "../components/Providers";
import "./globals.css";

export const metadata = {
  title: "SmartRoute",
  description: "Privacy-constrained academic document assistant",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#content">Skip to content</a>
        <Providers>
          <Nav />
          <main id="content" className="page">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
